"""LLM client for meeting summaries (SPEC 7.5, docs/summaries.md §LLM client).

OpenAI-compatible llama-server.  ``is_up()`` checks health; ``chat_json()``
sends a structured chat completion request and returns the validated result.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import get_settings


class _ActionItem(BaseModel):
    owner: str | None
    task: str
    due: str | None


class MeetingSummary(BaseModel):
    summary: str
    decisions: list[str]
    action_items: list[_ActionItem]
    open_questions: list[str]


class LlmError(Exception):
    """Raised when the LLM client cannot complete an operation."""


def get_llm_client() -> httpx.Client:
    """Return an httpx.Client configured for the LLM server."""
    settings = get_settings()
    return httpx.Client(
        base_url=settings.LLM_BASE_URL,
        headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
        timeout=settings.LLM_TIMEOUT_S,
    )


def is_up(client: httpx.Client | None = None) -> bool:
    """Check whether the LLM server is reachable (GET /models).

    Uses a 5-second timeout so a sleeping PC does not block the worker.
    """
    local_client = client or httpx.Client()
    try:
        resp = local_client.get("/models", timeout=5)
        return resp.status_code == 200
    except httpx.TimeoutException:
        return False
    except httpx.ConnectError:
        return False
    except httpx.NetworkError:
        return False
    except Exception:
        return False
    finally:
        if client is None:
            local_client.close()


def chat_json(
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Send a chat completion request and return the parsed JSON result.

    The request body follows the schema specified in docs/summaries.md §LLM
    client.  The response is parsed as JSON and validated against a pydantic
    schema; ``LlmError`` is raised on HTTP errors, bad JSON, or wrong shape.
    """
    settings = get_settings()
    local_client = client or httpx.Client()
    try:
        body = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 4096,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "meeting_summary",
                    "schema": schema,
                },
            },
        }

        resp = local_client.post(
            "/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            timeout=settings.LLM_TIMEOUT_S,
        )

        if not (200 <= resp.status_code < 300):
            raise LlmError(f"LLM returned status {resp.status_code}")

        payload = resp.json()
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise LlmError("Unexpected response shape from LLM") from None

        return json.loads(content)  # type: ignore[no-any-return]

    except LlmError:
        raise
    except json.JSONDecodeError:
        raise LlmError("LLM returned invalid JSON") from None
    except httpx.TimeoutException:
        raise LlmError("LLM request timed out") from None
    except httpx.ConnectError:
        raise LlmError("LLM connection refused") from None
    except Exception as exc:
        raise LlmError(f"LLM error: {exc}") from None
    finally:
        if client is None:
            local_client.close()

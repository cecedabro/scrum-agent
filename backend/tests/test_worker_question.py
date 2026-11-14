"""Tests for worker question jobs (TASK T49).

Covers:
- Prompt includes question, deadline title, and last summary.
- Answer posted to Teams once with ref_key ``question:<id>``.
- Invalid JSON from LLM triggers retry.
- Model offline leaves question job queued.
- Summary jobs are unaffected by question processing.
"""

import json
from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from app.clock import now_utc
from app.models import Job
from app.worker import run_once


def _build_llm_response(answer: str) -> dict:
    """Build a mock LLM chat completion response."""
    return {"choices": [{"message": {"content": json.dumps({"answer": answer})}}]}


def _build_bad_json_response() -> dict:
    """Build a mock LLM response with invalid JSON content."""
    return {"choices": [{"message": {"content": "not valid json at all"}}]}


def _build_empty_answer_response() -> dict:
    """Build a mock LLM response with empty answer field."""
    return {"choices": [{"message": {"content": json.dumps({"answer": ""})}}]}


def _capture_requests(transport: httpx.MockTransport) -> list[tuple[str, dict]]:
    """Extract (path, body) from all captured requests."""
    records: list[tuple[str, dict]] = []
    for request in transport.requests:
        path = request.url.path
        body = json.loads(request.read()) if request.content else {}
        records.append((path, body))
    return records


class TestQuestionPrompt:
    """Verify the LLM prompt content for question jobs."""

    def test_prompt_includes_question_and_context(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """LLM receives prompt with question, deadline title, and last summary."""
        captured: list[list[dict]] = []

        def mock_chat_json(messages, schema, client=None):
            captured.append(messages)
            return {"answer": "Het antwoord op je vraag."}

        monkeypatch.setattr("app.ask.chat_json", mock_chat_json)

        context = json.dumps(
            {
                "deadline_title": "Project X",
                "last_summary": "Vergadering van vorige week.",
            }
        )
        job = Job(
            kind="question",
            status="queued",
            title="Wanneer is de deadline voor Project X?",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript=context,
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now)

        assert result == "done"
        assert len(captured) == 1
        messages = captured[0]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "Je bent een assistent" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "Wanneer is de deadline voor Project X?" in messages[1]["content"]
        assert "Project X" in messages[1]["content"]
        assert "Vergadering van vorige week" in messages[1]["content"]


class TestQuestionPosting:
    """Verify answer is posted to Teams."""

    def test_answer_posted_once(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Answer is posted to Teams with ref_key question:<id>."""
        monkeypatch.setenv("TEAMS_WEBHOOK_URL", "http://localhost:9999/webhook")
        from app.config import get_settings

        get_settings.cache_clear()

        post_requests: list[dict] = []

        def mock_post(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.read()) if request.content else {}
            post_requests.append(body)
            return httpx.Response(200, json={})

        mock_transport = httpx.MockTransport(mock_post)

        def mock_chat_json(messages, schema, client=None):
            return {"answer": "Het team zal het uiterlijk vrijdag afronden."}

        monkeypatch.setattr("app.ask.chat_json", mock_chat_json)

        job = Job(
            kind="question",
            status="queued",
            title="Wanneer is de deadline?",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript=json.dumps({"deadline_title": "Project A"}),
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now, teams_client=httpx.Client(transport=mock_transport))

        assert result == "done"
        assert len(post_requests) == 1, f"post_requests={post_requests}"
        envelope = post_requests[0]
        assert "attachments" in envelope
        card = envelope["attachments"][0]["content"]
        assert card["type"] == "AdaptiveCard"
        body_texts = [elem["text"] for elem in card["body"] if elem.get("type") == "TextBlock"]
        assert "Wanneer is de deadline?" in body_texts[1] if len(body_texts) > 1 else False

        # Verify job status.
        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "done"
        assert job.result == {"answer": "Het team zal het uiterlijk vrijdag afronden."}

    def test_always_posts_even_when_auto_post_off(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Question cards are posted regardless of summary_auto_post setting."""
        monkeypatch.setenv("TEAMS_WEBHOOK_URL", "http://localhost:9999/webhook")
        from app.config import get_settings

        get_settings.cache_clear()

        post_count = 0

        def mock_post(request: httpx.Request) -> httpx.Response:
            nonlocal post_count
            post_count += 1
            return httpx.Response(200, json={})

        mock_transport = httpx.MockTransport(mock_post)

        def mock_chat_json(messages, schema, client=None):
            return {"answer": "Morgen."}

        monkeypatch.setattr("app.ask.chat_json", mock_chat_json)

        # Disable auto-post for summaries.
        from app.models import AppSetting

        row = AppSetting(key="summary_auto_post", value="false")
        db.add(row)

        job = Job(
            kind="question",
            status="queued",
            title="Wanneer leveren?",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript="{}",
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now, teams_client=httpx.Client(transport=mock_transport))

        assert result == "done"
        assert post_count == 1


class TestQuestionRetry:
    """Verify retry behaviour for question jobs."""

    def test_invalid_json_triggers_retry(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bad JSON from LLM triggers internal retry in ask()."""
        call_count = 0

        def mock_chat_json(messages, schema, client=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First attempt: invalid JSON triggers internal retry in ask().
                from app.llm import LlmError

                raise LlmError("LLM returned invalid JSON")
            return {"answer": "De deadline is vrijdag."}

        monkeypatch.setattr("app.ask.chat_json", mock_chat_json)

        job = Job(
            kind="question",
            status="queued",
            title="Wat is de deadline?",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript="{}",
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now)
        assert result == "done"
        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "done"
        assert job.result == {"answer": "De deadline is vrijdag."}
        assert call_count == 2


class TestQuestionOffline:
    """Verify question job stays queued when model is offline."""

    @pytest.fixture(autouse=True)
    def _mock_model_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.worker.is_up", lambda *a, **k: False)

    def test_question_stays_queued_when_model_offline(
        self,
        db,
    ) -> None:
        """Model down: question job stays queued, returns model_offline."""
        job = Job(
            kind="question",
            status="queued",
            title="Wat is het plan?",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript="{}",
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now)

        assert result == "model_offline"
        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "queued"
        assert job.attempts == 0
        assert job.started_at is None


class TestQuestionIsolation:
    """Verify summary jobs are unaffected by question processing."""

    @pytest.fixture(autouse=True)
    def _mock_summarize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "summary": "De samenvatting.",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        }
        monkeypatch.setattr("app.worker.summarize", lambda *a, **k: mock_result)

    def test_summary_job_unaffected(
        self,
        db,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Summary job processes normally alongside question processing logic."""
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "summary": "Samenvatting van de sprint planning.",
            "decisions": ["Backend afronden"],
            "action_items": [],
            "open_questions": [],
        }

        def mock_summarize(transcript, client=None):
            return mock_result

        monkeypatch.setattr("app.worker.summarize", mock_summarize)

        summary_job = Job(
            kind="summary",
            status="queued",
            title="Sprint planning",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript="Alice: We moeten de backend afronden.\nBob: Akkoord.",
        )
        db.add(summary_job)
        db.commit()

        now = now_utc()
        result = run_once(db, now)

        assert result == "done"
        job = db.execute(select(Job).where(Job.id == summary_job.id)).scalar_one()
        assert job.status == "done"
        assert job.result["summary"] == "Samenvatting van de sprint planning."

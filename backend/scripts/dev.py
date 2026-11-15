"""Bootstrap a local dev environment: pgserver, migrate, seed, fake LLM, uvicorn."""

import base64
import json
import os
import threading
from contextlib import suppress
from datetime import date, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import column, create_engine, insert, table
from uvicorn import Config, Server

BACKEND = Path(__file__).resolve().parents[1]
PGDATA = BACKEND / ".devdb"
FAKE_LLM_PORT = 18080

# ---------------------------------------------------------------------------
# Fake LLM server (in-process, single-threaded HTTP server)
# ---------------------------------------------------------------------------

_CANNED_SUMMARY = {
    "summary": "Dit is een test-samenvatting van het meetingtranscript.",
    "decisions": ["We gebruiken HTMX voor de frontend"],
    "action_items": [
        {"owner": "Squadder A", "task": "Deadline toevoegen", "due": "2026-01-15"},
        {"owner": "Squadder B", "task": "Teams webhook testen", "due": "2026-01-16"},
    ],
    "open_questions": ["Moeten we de retention days aanpassen?"],
}


def _fake_llm_handler() -> Any:
    """Return an httpx middleware function that serves canned summary JSON."""
    from fastapi import FastAPI
    from pydantic import BaseModel, Field

    class MessageItem(BaseModel):
        role: str
        content: str

    class RequestBody(BaseModel):
        model: str = ""
        messages: list[MessageItem] = Field(default_factory=list)
        temperature: float = 0.2
        max_tokens: int = 4096

    fake_app = FastAPI(title="Fake LLM for dev")

    @fake_app.post("/chat/completions")
    def chat_completions(body: RequestBody) -> dict[str, Any]:  # noqa: ARG001
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(_CANNED_SUMMARY, ensure_ascii=False),
                    }
                }
            ]
        }

    @fake_app.get("/models")
    def models() -> dict[str, Any]:
        return {"data": [{"id": "fake-coder", "object": "model"}]}

    return fake_app, FAKE_LLM_PORT


def _run_fake_llm(app: Any, port: int) -> None:
    """Run the fake LLM FastAPI app in a daemon thread."""

    config = Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    uvicorn_server = Server(config=config)
    uvicorn_server.run()


# ---------------------------------------------------------------------------
# pgserver lifecycle
# ---------------------------------------------------------------------------


def _start_pgserver() -> str:
    """Start a pgserver instance, return the database URL."""
    import pgserver

    pgdata = Path(".devdb")
    if not pgdata.exists():
        pgdata.mkdir(parents=True, exist_ok=True)

    srv = pgserver.get_server(pgdata)
    url = srv.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)
    return url, srv


# ---------------------------------------------------------------------------
# Migration helper
# ---------------------------------------------------------------------------


def _migrate(database_url: str) -> None:
    """Run alembic upgrade to head."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------


def _seed(database_url: str, fake_llm_port: int) -> None:
    """Insert 4 deadlines relative to today and one finished summary job."""
    today = date.today()
    engine = create_engine(database_url, isolation_level="AUTOCOMMIT")

    # Seed deadlines
    deadlines = [
        {
            "title": "Sprint Planning voorbereiden",
            "due_date": today + timedelta(days=1),
            "due_time": dt_time(9, 0),
            "note": "Agenda en backlog klaarleggen",
            "source": "manual",
            "external_ref": None,
        },
        {
            "title": "Retrospective notulen",
            "due_date": today + timedelta(days=3),
            "due_time": dt_time(14, 30),
            "note": "Actiepunten uit de retro verwerken",
            "source": "manual",
            "external_ref": None,
        },
        {
            "title": "Demo presentatie",
            "due_date": today + timedelta(days=7),
            "due_time": dt_time(10, 0),
            "note": "Functionaliteit tonen aan stakeholder",
            "source": "manual",
            "external_ref": None,
        },
        {
            "title": "Code review pull request",
            "due_date": today + timedelta(days=14),
            "due_time": None,
            "note": "Review PR #42 voor integratietest",
            "source": "github",
            "external_ref": "refs/pull/42/head",
        },
    ]

    # Seed a finished summary job
    summary_job = {
        "kind": "summary",
        "status": "done",
        "title": "Testmeeting samenvatting",
        "meeting_date": today - timedelta(days=2),
        "transcript": None,
        "result": json.dumps(_CANNED_SUMMARY, ensure_ascii=False),
        "error": None,
        "attempts": 1,
    }

    deadline_tbl = table(
        "deadline",
        column("title"),
        column("due_date"),
        column("due_time"),
        column("note"),
        column("source"),
        column("external_ref"),
    )
    job_tbl = table(
        "job",
        column("kind"),
        column("status"),
        column("title"),
        column("meeting_date"),
        column("transcript"),
        column("result"),
        column("error"),
        column("attempts"),
    )

    with engine.connect() as conn:
        for dl in deadlines:
            conn.execute(insert(deadline_tbl).values(**dl))
        conn.execute(insert(job_tbl).values(**summary_job))
        conn.commit()

    engine.dispose()

    # Store fake LLM base URL in app_settings
    from app.config import get_settings

    # Set LLM_BASE_URL via environment for the running app
    os.environ["LLM_BASE_URL"] = f"http://localhost:{fake_llm_port}/v1"
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Auth header helper
# ---------------------------------------------------------------------------


def _get_basic_auth_header() -> dict[str, str]:
    """Return basic auth headers for the dev environment."""
    from app.config import get_settings

    settings = get_settings()
    encoded = base64.b64encode(f"{settings.TEAM_USER}:{settings.TEAM_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Bootstrap and run the dev server."""
    # 1. Start pgserver
    print("Starting pgserver...")
    database_url, srv = _start_pgserver()
    os.environ["DATABASE_URL"] = database_url
    print(f"Postgres: {database_url}")

    try:
        # 2. Migrate
        print("Running migrations...")
        _migrate(database_url)
        print("Migrations complete.")

        # 3. Start fake LLM in a background thread
        print(f"Starting fake LLM on port {FAKE_LLM_PORT}...")
        fake_app, port = _fake_llm_handler()
        llm_thread = threading.Thread(target=_run_fake_llm, args=(fake_app, port), daemon=True)
        llm_thread.start()

        # Wait for fake LLM to be ready
        http_client = httpx.Client()
        for _ in range(30):
            try:
                resp = http_client.get(f"http://localhost:{port}/models", timeout=1)
            except httpx.ConnectError:
                pass
            else:
                if resp.status_code == 200:
                    break
            httpx.Client().close()
            http_client.close()
            http_client = httpx.Client()
            import time

            time.sleep(0.2)
        http_client.close()
        print(f"Fake LLM ready on port {port}.")

        # 4. Seed data
        print("Seeding deadlines and summary job...")
        _seed(database_url, port)
        print("Seed complete: 4 deadlines, 1 finished summary job.")

        # 5. Run uvicorn
        print("Starting dev server on :8000...")
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",  # noqa: S104
            port=8000,
            reload=False,
            log_level="info",
        )
    finally:
        print("Cleaning up pgserver...")
        with suppress(Exception):
            srv.cleanup()  # type: ignore[attr-defined]
        print("Done.")


if __name__ == "__main__":
    main()

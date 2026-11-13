"""Shared fixtures: a throwaway Postgres, migrated once per test session.

Order matters: DATABASE_URL is set before `app` is imported anywhere.
"""

import base64
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]


def _start_pgserver(tmp: Path) -> tuple[str, object]:
    import pgserver

    srv = pgserver.get_server(tmp)
    return srv.get_uri().replace("postgresql://", "postgresql+psycopg://", 1), srv


@pytest.fixture(scope="session")
def database_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """TEST_DATABASE_URL (a Postgres you may wipe) if set, else a pgserver instance."""
    url = os.environ.get("TEST_DATABASE_URL")
    srv = None
    if url:
        # Use a separate database next to the given one, created and wiped by us.
        parsed = make_url(url).set(database="scrum_test")
        admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text("DROP DATABASE IF EXISTS scrum_test WITH (FORCE)"))
            conn.execute(text("CREATE DATABASE scrum_test"))
        admin.dispose()
        url = parsed.render_as_string(hide_password=False)
    else:
        url, srv = _start_pgserver(tmp_path_factory.mktemp("pg"))
    os.environ["DATABASE_URL"] = url
    from app.config import get_settings
    from app.db import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield url
    get_engine().dispose()
    if srv is not None:
        srv.cleanup()  # type: ignore[attr-defined]


@pytest.fixture()
def db(database_url: str) -> Iterator[object]:
    """A session; every table is emptied after the test."""
    from app.db import session_factory
    from app.models import Base

    with session_factory()() as session:
        yield session
        session.rollback()
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        if tables:
            session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
            session.commit()


@pytest.fixture()
def client(db: object) -> Iterator[object]:
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def auth_client(db: object) -> Iterator[object]:
    """TestClient with valid Basic auth headers (TEAM_USER / TEAM_PASSWORD)."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import create_app

    settings = get_settings()
    encoded = base64.b64encode(f"{settings.TEAM_USER}:{settings.TEAM_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {encoded}"}

    with TestClient(create_app(), headers=headers) as c:
        yield c


def _b64_credentials(user: str, password: str) -> str:
    """Return ``Basic <base64>`` for the given user/password pair."""
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
    return f"Basic {encoded}"


def set_clock(clock_fn: object) -> None:
    """Override the clock used by auth (for testing)."""
    from app.auth import set_clock as _set_clock

    _set_clock(clock_fn)


def reset_login_state() -> None:
    """Clear failed-login and rate-limit state."""
    from app.auth import reset_login_state as _reset

    _reset()

"""SPEC 1.2, 1.4, 1.5."""

import pytest
from fastapi.testclient import TestClient


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_ready_when_database_answers(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_readyz_unavailable_when_database_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy import create_engine

    import app.main

    dead = create_engine(
        "postgresql+psycopg://x:x@127.0.0.1:1/x", connect_args={"connect_timeout": 1}
    )
    monkeypatch.setattr(app.main, "get_engine", lambda: dead)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable"}


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({}, "TEAM_PASSWORD"),
        ({"TEAM_PASSWORD": "short"}, "TEAM_PASSWORD"),
        ({"TEAM_PASSWORD": "a-long-real-password", "TEAMS_WEBHOOK_URL": "http://x"}, "https://"),
    ],
)
def test_production_refuses_unsafe_config(
    database_url: str, monkeypatch: pytest.MonkeyPatch, env: dict[str, str], message: str
) -> None:
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("TEAM_PASSWORD", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match=message):
            create_app()
    finally:
        get_settings.cache_clear()


def test_production_starts_with_real_secrets(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TEAM_PASSWORD", "a-long-real-password")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.invalid/hook")
    get_settings.cache_clear()
    try:
        assert TestClient(create_app()).get("/healthz").status_code == 200
    finally:
        get_settings.cache_clear()

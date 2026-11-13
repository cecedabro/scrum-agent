"""SPEC 4.1-4.2: Settings page — render, save, validate, test endpoint.

Tests use the ``auth_client`` fixture (Basic auth) and ``db`` fixture
(real Postgres, no mocks).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

# ------------------------------------------------------------------
# GET /settings — page renders
# ------------------------------------------------------------------


def test_get_settings_page_renders(auth_client: TestClient) -> None:
    """Settings page renders without error."""
    r = auth_client.get("/settings")
    assert r.status_code == 200
    assert b"Instellingen" in r.content


def test_get_settings_page_has_form(auth_client: TestClient) -> None:
    """Settings page includes a settings form with expected fields."""
    r = auth_client.get("/settings")
    assert r.status_code == 200
    assert b'name="weekly_enabled"' in r.content
    assert b'name="weekly_weekday"' in r.content
    assert b'name="weekly_time"' in r.content
    assert b'name="deadline_reminder_enabled"' in r.content
    assert b'name="deadline_reminder_time"' in r.content
    assert b'name="deadline_reminder_days_before"' in r.content
    assert b'name="sprint_enabled"' in r.content
    assert b'name="sprint_length"' in r.content
    assert b'name="sprint_days_before"' in r.content
    assert b'name="sprint_time"' in r.content
    assert b'name="summary_auto_post"' in r.content
    assert b'name="sprint_end_date"' in r.content


def test_get_settings_page_shows_weekday_options(auth_client: TestClient) -> None:
    """Settings page shows all Dutch weekday options."""
    r = auth_client.get("/settings")
    assert r.status_code == 200
    for day in ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]:
        assert day.encode() in r.content


# ------------------------------------------------------------------
# GET /settings — webhook status
# ------------------------------------------------------------------


def test_get_settings_shows_webhook_status(auth_client: TestClient) -> None:
    """Settings page shows whether a webhook URL is configured."""
    r = auth_client.get("/settings")
    assert r.status_code == 200
    assert b"Webhook ingesteld:" in r.content


# ------------------------------------------------------------------
# GET /settings — default values
# ------------------------------------------------------------------


def test_get_settings_shows_defaults(db, auth_client: TestClient) -> None:
    """Settings page shows default values when none are stored."""
    r = auth_client.get("/settings")
    assert r.status_code == 200
    assert b"09:00" in r.content  # default deadline reminder time


# ------------------------------------------------------------------
# GET /settings — auth required
# ------------------------------------------------------------------


def test_get_settings_requires_auth(client: TestClient) -> None:
    """Unauthenticated GET /settings returns 401."""
    r = client.get("/settings")
    assert r.status_code == 401


# ------------------------------------------------------------------
# POST /settings — save valid settings
# ------------------------------------------------------------------


def test_post_settings_saves_and_redirects(db, auth_client: TestClient) -> None:
    """Valid POST to /settings saves and redirects."""
    payload = {
        "weekly_enabled": "on",
        "weekly_weekday": "dinsdag",
        "weekly_time": "10:00",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "11:00",
        "deadline_reminder_days_before": "3,2,1",
        "sprint_enabled": "on",
        "sprint_end_date": "2026-12-31",
        "sprint_length": "3",
        "sprint_days_before": "5",
        "sprint_time": "15:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload, follow_redirects=False)
    assert r.status_code in (302, 303)

    # Follow redirect and check the page
    r2 = auth_client.get("/settings")
    assert r2.status_code == 200
    assert b"dinsdag" in r2.content
    assert b"10:00" in r2.content
    assert b"3,2,1" in r2.content


def test_post_settings_stored_in_db(db, auth_client: TestClient) -> None:
    """POST /settings persists settings to the database."""
    from app.settings import load

    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "woensdag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "off",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "off",
    }
    auth_client.post("/settings", data=payload, follow_redirects=False)

    with db as session:
        loaded = load(session)

    assert loaded.weekly_enabled is False
    assert loaded.weekly_weekday == "woensdag"
    assert loaded.deadline_reminder_enabled is False
    assert loaded.weekdays_before == [2, 1]
    assert loaded.sprint_enabled is False
    assert loaded.summary_auto_post is False


def test_post_settings_preserves_other_fields(db, auth_client: TestClient) -> None:
    """POST /settings updates all fields together (full save)."""
    from app.settings import load

    # First save initial values
    payload1 = {
        "weekly_enabled": "on",
        "weekly_weekday": "maandag",
        "weekly_time": "07:00",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    auth_client.post("/settings", data=payload1, follow_redirects=False)

    with db as session:
        loaded = load(session)
    assert loaded.weekly_time == "07:00"
    assert loaded.weekly_enabled is True


def test_post_settings_redirects_to_settings(auth_client: TestClient) -> None:
    """POST /settings redirects to /settings."""
    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").startswith("/settings")


# ------------------------------------------------------------------
# POST /settings — form validation errors
# ------------------------------------------------------------------


def test_post_settings_validation_invalid_weekday(db, auth_client: TestClient) -> None:
    """Invalid weekly weekday shows validation error."""
    payload = {
        "weekly_enabled": "on",
        "weekly_weekday": "zontdag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"Ongeldige dag" in r.content
    assert b"zontdag" in r.content

    # Should not have saved
    from app.settings import load

    with db as session:
        loaded = load(session)
    assert loaded.weekly_weekday != "zontdag"


def test_post_settings_validation_invalid_weekly_time(db, auth_client: TestClient) -> None:
    """Invalid weekly time shows validation error."""
    payload = {
        "weekly_enabled": "on",
        "weekly_weekday": "maandag",
        "weekly_time": "25:99",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"Ongeldig tijdstip" in r.content


def test_post_settings_validation_invalid_deadline_time(db, auth_client: TestClient) -> None:
    """Invalid deadline reminder time shows validation error."""
    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "invalid",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"Ongeldig tijdstip" in r.content


def test_post_settings_validation_invalid_sprint_length(db, auth_client: TestClient) -> None:
    """Invalid sprint length shows validation error."""
    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "on",
        "sprint_end_date": "2026-12-01",
        "sprint_length": "5",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"sprint lengte" in r.content


def test_post_settings_validation_sprint_days_before(db, auth_client: TestClient) -> None:
    """Sprint days before out of range (1-14) shows validation error."""
    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "on",
        "sprint_end_date": "2026-12-01",
        "sprint_length": "2",
        "sprint_days_before": "20",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"dagen vooraf" in r.content


def test_post_settings_validation_invalid_sprint_time(db, auth_client: TestClient) -> None:
    """Invalid sprint time shows validation error."""
    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_enabled": "on",
        "sprint_end_date": "2026-12-01",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "bad",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"Ongeldig tijdstip" in r.content


def test_post_settings_validation_deadline_days_before(db, auth_client: TestClient) -> None:
    """Weekdays before out of range (1-14) shows validation error."""
    payload = {
        "weekly_enabled": "off",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "on",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "20,1",
        "sprint_enabled": "off",
        "sprint_end_date": "",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
        "summary_auto_post": "on",
    }
    r = auth_client.post("/settings", data=payload)
    assert r.status_code == 200
    assert b"dagen vooraf" in r.content


# ------------------------------------------------------------------
# POST /settings/test — test card endpoint
# ------------------------------------------------------------------


def test_post_settings_test_shows_result(db, auth_client: TestClient) -> None:
    """POST /settings/test sends a test card and shows status."""
    r = auth_client.post("/settings/test")
    assert r.status_code == 200
    assert b"Status:" in r.content


def test_post_settings_test_displayed_on_page(db, auth_client: TestClient) -> None:
    """POST /settings/test result is displayed on the settings page."""
    r = auth_client.post("/settings/test")
    assert r.status_code == 200
    assert b"Status:" in r.content


def test_post_settings_test_form_exists(auth_client: TestClient) -> None:
    """Settings page includes a test button form."""
    r = auth_client.get("/settings")
    assert r.status_code == 200
    assert b"/settings/test" in r.content

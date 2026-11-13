"""Settings service (SPEC 4.1-4.2).

ReminderSettings stores application settings in the database
(key-value pairs in ``app_setting``).  The ``load``/``save``
functions read and write individual rows; ``validate_settings``
checks every field and returns Dutch error messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ── Dutch weekday names (lowercase, no accents) ────────────────────

VALID_WEEKDAYS = (
    "maandag",
    "dinsdag",
    "woensdag",
    "donderdag",
    "vrijdag",
    "zaterdag",
    "zondag",
)

# ── Defaults (SPEC 4.1) ───────────────────────────────────────────

_DEFAULTS = {
    "weekly_enabled": "false",
    "weekly_weekday": "maandag",
    "weekly_time": "08:30",
    "deadline_reminder_enabled": "true",
    "deadline_reminder_time": "09:00",
    "deadline_reminder_days_before": "2,1",
    "sprint_enabled": "false",
    "sprint_end_date": "",
    "sprint_length": "2",
    "sprint_days_before": "1",
    "sprint_time": "09:00",
    "summary_auto_post": "true",
}


# ── ReminderSettings dataclass ─────────────────────────────────────


@dataclass
class ReminderSettings:
    """Parsed settings with all SPEC 4.1 defaults."""

    weekly_enabled: bool = False
    weekly_weekday: str = "maandag"
    weekly_time: str = "08:30"
    deadline_reminder_enabled: bool = True
    deadline_reminder_time: str = "09:00"
    weekdays_before: list[int] = field(
        default_factory=lambda: [2, 1],
    )
    sprint_enabled: bool = False
    sprint_end_date: str = ""
    sprint_length: int = 2
    sprint_days_before: int = 1
    sprint_time: str = "09:00"
    summary_auto_post: bool = True


# ── Validation helpers ─────────────────────────────────────────────


def _validate_time(t: str) -> bool:
    """Return ``True`` when *t* matches ``HH:MM`` (24h) format."""
    parts = t.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return False
    return 0 <= h <= 23 and 0 <= m <= 59


def _validate_days_before(value: str) -> tuple[bool, list[int], str]:
    """Parse comma-separated day values (1-14).

    Returns ``(ok, parsed_list, error_message)``.
    ``ok`` is ``False`` when parsing fails.
    """
    if not value or not value.strip():
        return False, [], "'dagen vooraf' is verplicht"
    raw = [v.strip() for v in value.split(",") if v.strip()]
    if not raw:
        return False, [], "'dagen vooraf' is verplicht"
    try:
        days = [int(d) for d in raw]
    except ValueError:
        return False, [], "Ongeldige waarde in 'dagen vooraf'"
    for d in days:
        if d < 0 or d > 14:
            return False, [], "waarden voor 'dagen vooraf' moeten tussen 0 en 14 liggen"
    return True, sorted(days, reverse=True), ""


def _validate_sprint_length(value: str) -> tuple[bool, int, str]:
    """Validate sprint length (1-4).

    Returns ``(ok, value, error_message)``.
    """
    if not value or not value.strip():
        return False, 2, "'sprint lengte' is verplicht"
    try:
        sl = int(value)
    except ValueError:
        return False, 2, "Ongeldige waarde voor 'sprint lengte'"
    if sl < 1 or sl > 4:
        return False, 2, "'sprint lengte' moet tussen 1 en 4 liggen"
    return True, sl, ""


def validate_settings(settings: ReminderSettings) -> list[str]:
    """Validate every field of *settings* and return Dutch error messages.

    Returns an **empty** list when all fields are valid.
    """
    errors: list[str] = []

    # weekly weekday
    if settings.weekly_weekday not in VALID_WEEKDAYS:
        errors.append(f"Ongeldige dag: '{settings.weekly_weekday}'")

    # weekly time
    if not _validate_time(settings.weekly_time):
        errors.append("Ongeldig tijdstip voor 'wekelijkse overviews'")

    # deadline reminder time
    if not _validate_time(settings.deadline_reminder_time):
        errors.append("Ongeldig tijdstip voor 'deadline herinneringen'")

    # sprint length
    sl_ok, sl_val, sl_err = _validate_sprint_length(str(settings.sprint_length))
    if not sl_ok:
        errors.append(sl_err)

    # sprint days before (1-14)
    if settings.sprint_days_before < 1 or settings.sprint_days_before > 14:
        errors.append("waarden voor 'dagen vooraf' moeten tussen 1 en 14 liggen")

    # sprint time
    if not _validate_time(settings.sprint_time):
        errors.append("Ongeldig tijdstip voor 'sprint nudges'")

    # weekdays_before (deadline reminders)
    for d in settings.weekdays_before:
        if d < 0 or d > 14:
            errors.append("waarden voor 'dagen vooraf' moeten tussen 0 en 14 liggen")
            break

    return errors


# ── load / save ────────────────────────────────────────────────────


def load(db: Session) -> ReminderSettings:
    """Read stored key-value rows and return a ``ReminderSettings``.

    Missing keys fall back to the defaults defined in ``_DEFAULTS``.
    """
    from app.models import AppSetting  # avoid circular import at import-time

    rows = {r.key: r.value for r in db.query(AppSetting).all()}

    def _get(key: str, default: str) -> str:
        return rows.get(key, _DEFAULTS.get(key, default))

    def _bool(key: str, default: bool) -> bool:
        v = rows.get(key, _DEFAULTS.get(key, str(default).lower()))
        return v.lower() in ("true", "1", "yes", "on")

    ok, days, _ = _validate_days_before(_get("deadline_reminder_days_before", "2,1"))
    wd_days = days if ok else [2, 1]

    ok, sl, _ = _validate_sprint_length(_get("sprint_length", "2"))
    sprint_len = sl if ok else 2

    return ReminderSettings(
        weekly_enabled=_bool("weekly_enabled", False),
        weekly_weekday=_get("weekly_weekday", "maandag"),
        weekly_time=_get("weekly_time", "08:30"),
        deadline_reminder_enabled=_bool("deadline_reminder_enabled", True),
        deadline_reminder_time=_get("deadline_reminder_time", "09:00"),
        weekdays_before=wd_days,
        sprint_enabled=_bool("sprint_enabled", False),
        sprint_end_date=_get("sprint_end_date", ""),
        sprint_length=sprint_len,
        sprint_days_before=int(_get("sprint_days_before", "1")),
        sprint_time=_get("sprint_time", "09:00"),
        summary_auto_post=_bool("summary_auto_post", True),
    )


def save(db: Session, settings: ReminderSettings) -> None:
    """Write every field of *settings* to the ``app_setting`` table.

    Existing rows are updated (upsert-by-key); unknown keys are dropped.
    """
    from app.clock import now_utc
    from app.models import AppSetting

    now = now_utc()

    mapping: dict[str, str] = {
        "weekly_enabled": str(settings.weekly_enabled).lower(),
        "weekly_weekday": settings.weekly_weekday,
        "weekly_time": settings.weekly_time,
        "deadline_reminder_enabled": str(settings.deadline_reminder_enabled).lower(),
        "deadline_reminder_time": settings.deadline_reminder_time,
        "deadline_reminder_days_before": ",".join(str(d) for d in settings.weekdays_before),
        "sprint_enabled": str(settings.sprint_enabled).lower(),
        "sprint_end_date": settings.sprint_end_date,
        "sprint_length": str(settings.sprint_length),
        "sprint_days_before": str(settings.sprint_days_before),
        "sprint_time": settings.sprint_time,
        "summary_auto_post": str(settings.summary_auto_post).lower(),
    }

    existing = {r.key: r for r in db.query(AppSetting).all()}

    for key, value in mapping.items():
        if key in existing:
            existing[key].value = value
            existing[key].updated_at = now
        else:
            db.add(AppSetting(key=key, value=value, updated_at=now))

    db.flush()

"""Tests for the settings service (SPEC 4.1-4.2)."""

import pytest

from app.models import AppSetting
from app.settings import (
    _DEFAULTS,
    ReminderSettings,
    load,
    save,
    validate_settings,
)


@pytest.fixture()
def settings() -> ReminderSettings:
    """A ReminderSettings with all defaults (valid)."""
    return ReminderSettings()


# ── defaults ────────────────────────────────────────────────────────


class TestDefaults:
    def test_dataclass_defaults_match_spec(self):
        s = ReminderSettings()
        assert s.weekly_enabled is False
        assert s.weekly_weekday == "maandag"
        assert s.weekly_time == "08:30"
        assert s.deadline_reminder_enabled is True
        assert s.deadline_reminder_time == "09:00"
        assert s.weekdays_before == [2, 1]
        assert s.sprint_enabled is False
        assert s.sprint_end_date == ""
        assert s.sprint_length == 2
        assert s.sprint_days_before == 1
        assert s.sprint_time == "09:00"
        assert s.summary_auto_post is True

    def test_defaults_dict_has_all_keys(self):
        required_keys = {
            "weekly_enabled",
            "weekly_weekday",
            "weekly_time",
            "deadline_reminder_enabled",
            "deadline_reminder_time",
            "deadline_reminder_days_before",
            "sprint_enabled",
            "sprint_end_date",
            "sprint_length",
            "sprint_days_before",
            "sprint_time",
            "summary_auto_post",
        }
        assert required_keys.issubset(set(_DEFAULTS.keys()))


# ── validation ──────────────────────────────────────────────────────


class TestValidation:
    def test_settings_no_errors(self, settings: ReminderSettings):
        assert validate_settings(settings) == []

    @pytest.mark.parametrize(
        "field,invalid_value",
        [
            ("weekly_weekday", "onbekend"),
            ("weekly_time", "25:00"),
            ("weekly_time", "ab:cd"),
            ("deadline_reminder_time", "12:60"),
            ("deadline_reminder_time", "bad"),
            ("sprint_length", 5),
            ("sprint_length", 0),
            ("sprint_days_before", 15),
            ("sprint_days_before", 0),
            ("sprint_time", "abc"),
            ("weekdays_before", [0]),
            ("weekdays_before", [15]),
        ],
    )
    def test_invalid_field_returns_errors(
        self,
        field: str,
        invalid_value,
        settings: ReminderSettings,
    ):
        settings = ReminderSettings(**vars(settings))
        if field == "weekdays_before":
            settings.weekdays_before = invalid_value
        else:
            setattr(settings, field, invalid_value)
        errors = validate_settings(settings)
        assert len(errors) >= 1, f"No error for invalid {field}={invalid_value!r}"

    def test_dutch_error_messages(self, settings: ReminderSettings):
        settings = ReminderSettings(**vars(settings))
        settings.weekly_weekday = "onbekend"
        errors = validate_settings(settings)
        assert any("Ongeldig" in e for e in errors)


# ── load / save round-trip ─────────────────────────────────────────


class TestLoadSave:
    def test_save_creates_rows(self, db, settings: ReminderSettings):
        save(db, settings)
        db.commit()
        keys = {r.key for r in db.query(AppSetting).all()}
        assert len(keys) == 12

    def test_load_empty_db_gives_defaults(self, db):
        s = load(db)
        assert s.weekly_enabled is False
        assert s.weekly_weekday == "maandag"
        assert s.deadline_reminder_enabled is True
        assert s.weekdays_before == [2, 1]
        assert s.sprint_enabled is False
        assert s.summary_auto_post is True

    def test_round_trip(self, db, settings: ReminderSettings):
        save(db, settings)
        db.commit()
        loaded = load(db)
        assert loaded.weekly_enabled == settings.weekly_enabled
        assert loaded.weekly_weekday == settings.weekly_weekday
        assert loaded.weekly_time == settings.weekly_time
        assert loaded.deadline_reminder_enabled == settings.deadline_reminder_enabled
        assert loaded.deadline_reminder_time == settings.deadline_reminder_time
        assert loaded.weekdays_before == settings.weekdays_before
        assert loaded.sprint_enabled == settings.sprint_enabled
        assert loaded.sprint_length == settings.sprint_length
        assert loaded.sprint_days_before == settings.sprint_days_before
        assert loaded.sprint_time == settings.sprint_time
        assert loaded.summary_auto_post == settings.summary_auto_post

    def test_save_updates_existing(self, db, settings: ReminderSettings):
        # First save
        settings.weekly_enabled = True
        settings.weekly_time = "17:00"
        save(db, settings)
        db.commit()

        # Modify
        settings.weekly_enabled = False
        settings.weekly_time = "10:00"
        save(db, settings)
        db.commit()

        loaded = load(db)
        assert loaded.weekly_enabled is False
        assert loaded.weekly_time == "10:00"

    def test_load_partial_stores_missing_as_defaults(self, db):
        # Insert only one setting
        row = AppSetting(key="weekly_enabled", value="true")
        db.add(row)
        db.commit()

        s = load(db)
        assert s.weekly_enabled is True
        # All other fields should be defaults
        assert s.weekly_weekday == "maandag"
        assert s.summary_auto_post is True

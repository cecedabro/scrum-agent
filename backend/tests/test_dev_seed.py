"""Tests for the seed function in backend/scripts/dev.py."""

import json
import os
import sys
from datetime import date, timedelta
from datetime import time as dt_time
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear cached settings/engine before each test."""
    from app.config import get_settings
    from app.db import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()


class TestSeedDeadlines:
    """Test that the seed function inserts the correct deadlines."""

    def test_seed_inserts_four_deadlines(self, db: object, database_url: str):
        """Seed should insert exactly 4 deadlines."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM deadline")).scalar_one()
            assert count == 4
        engine.dispose()

    def test_seed_deadlines_have_correct_dates(self, db: object, database_url: str):
        """Seed deadlines should have dates relative to today."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        today = date.today()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT due_date FROM deadline ORDER BY due_date")).all()
            due_dates = [row[0] for row in rows]
            expected_dates = [
                today + timedelta(days=1),
                today + timedelta(days=3),
                today + timedelta(days=7),
                today + timedelta(days=14),
            ]
            assert due_dates == expected_dates
        engine.dispose()

    def test_seed_deadlines_have_correct_titles(self, db: object, database_url: str):
        """Seed deadlines should have the expected Dutch titles."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT title FROM deadline ORDER BY due_date")).all()
            titles = [row[0] for row in rows]
            assert titles[0] == "Sprint Planning voorbereiden"
            assert titles[1] == "Retrospective notulen"
            assert titles[2] == "Demo presentatie"
            assert titles[3] == "Code review pull request"
        engine.dispose()

    def test_seed_deadlines_have_correct_sources(self, db: object, database_url: str):
        """Seed deadlines should have correct source values."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT source FROM deadline ORDER BY due_date")).all()
            sources = [row[0] for row in rows]
            assert sources[0] == "manual"
            assert sources[1] == "manual"
            assert sources[2] == "manual"
            assert sources[3] == "github"
        engine.dispose()

    def test_seed_deadline_has_time(self, db: object, database_url: str):
        """First deadline should have a due_time set."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT due_time FROM deadline WHERE title = 'Sprint Planning voorbereiden'")
            ).one_or_none()
            assert row is not None
            assert row[0] == dt_time(9, 0)
        engine.dispose()

    def test_seed_deadline_without_time(self, db: object, database_url: str):
        """Last deadline should have no due_time."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT due_time FROM deadline WHERE title = 'Code review pull request'")
            ).one_or_none()
            assert row is not None
            assert row[0] is None
        engine.dispose()


class TestSeedSummaryJob:
    """Test that the seed function inserts the correct summary job."""

    def test_seed_inserts_one_summary_job(self, db: object, database_url: str):
        """Seed should insert exactly 1 summary job."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM job")).scalar_one()
            assert count == 1
        engine.dispose()

    def test_seed_summary_job_status_is_done(self, db: object, database_url: str):
        """Seed summary job should have status 'done'."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT status FROM job")).one_or_none()
            assert row[0] == "done"
        engine.dispose()

    def test_seed_summary_job_has_result(self, db: object, database_url: str):
        """Seed summary job should have a JSON result."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT result FROM job")).one_or_none()
            assert row is not None
            result = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            assert "summary" in result
            assert "decisions" in result
            assert "action_items" in result
            assert "open_questions" in result
        engine.dispose()

    def test_seed_summary_job_is_recent(self, db: object, database_url: str):
        """Seed summary job meeting_date should be within last 3 days."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        os.environ["DATABASE_URL"] = database_url
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        engine = create_engine(database_url)
        with engine.connect() as conn:
            row = conn.execute(text("SELECT meeting_date FROM job")).one_or_none()
            meeting_date = row[0]
            today = date.today()
            assert meeting_date >= today - timedelta(days=3)
            assert meeting_date <= today - timedelta(days=1)
        engine.dispose()


class TestSeedFakeLLMConfig:
    """Test that the seed function configures the fake LLM."""

    def test_seed_sets_llm_base_url(self, db: object, database_url: str):
        """Seed should set LLM_BASE_URL in environment."""
        import importlib.util

        spec = importlib.util.spec_from_file_location("dev", BACKEND / "scripts" / "dev.py")
        dev_mod = importlib.util.module_from_spec(spec)  # type: ignore[union-attr]

        # Clear any existing LLM_BASE_URL
        old = os.environ.pop("LLM_BASE_URL", None)
        from app.config import get_settings

        get_settings.cache_clear()

        spec.loader.exec_module(dev_mod)  # type: ignore[union-attr]

        dev_mod._seed(database_url, 18080)

        assert "LLM_BASE_URL" in os.environ
        assert os.environ["LLM_BASE_URL"] == "http://localhost:18080/v1"

        if old is not None:
            os.environ["LLM_BASE_URL"] = old
        else:
            os.environ.pop("LLM_BASE_URL", None)

"""Helpers for check-migrations.sh. Run inside a checkout's backend/ directory.

Data goes in and comes out only through the deadlines API (SPEC 3.5), so the check
works across versions whatever the table names are. Until that API exists, the
data check is skipped (the schema checks in the script still run).

    python migcheck.py wipe | seed | verify
"""

import base64
import os
import sys

sys.path.insert(0, os.getcwd())  # the checkout's backend/, so `app` is importable

AUTH = (os.environ.get("TEAM_USER", "team"), os.environ.get("TEAM_PASSWORD", "dev-password"))
SAMPLE = {"title": "Migcheck sprint review", "due_date": "2030-01-18", "note": "do not lose me"}


def wipe() -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import OperationalError

    url = make_url(os.environ["DATABASE_URL"])
    try:
        create_engine(url).connect().close()
    except OperationalError:  # database missing: create it from the server's default db
        admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    with create_engine(url).begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


def client():  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from app.main import app

    token = base64.b64encode(f"{AUTH[0]}:{AUTH[1]}".encode()).decode()
    return TestClient(app, headers={"Authorization": f"Basic {token}"})


def seed() -> None:
    r = client().post("/api/v1/deadlines", json=SAMPLE)
    if r.status_code == 404:
        print("no /api/v1/deadlines yet: skipping the data check")
        return
    assert r.status_code == 201, r.text
    print("seeded 1 deadline")


def verify() -> None:
    r = client().get("/api/v1/deadlines", params={"include_past": "true"})
    if r.status_code == 404:
        print("no /api/v1/deadlines yet: skipping the data check")
        return
    assert r.status_code == 200, r.text
    found = [d for d in r.json() if d.get("title") == SAMPLE["title"]]
    assert found, f"deadline lost after upgrade: {r.text}"
    assert found[0]["due_date"] == SAMPLE["due_date"] and found[0]["note"] == SAMPLE["note"]
    print("data intact after upgrade")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "?"
    {"wipe": wipe, "seed": seed, "verify": verify}[cmd]()

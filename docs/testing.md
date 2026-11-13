# Testing (read this — you write the tests)

The harness decides a task is done by running its `accept:` command and `make check`. A
weak test that passes without proving the behaviour is a **failed task**, not a shortcut.

## The one rule
Every test asserts a behaviour named in `SPEC.md`, with a concrete expected value.

## Fixtures you already have (`backend/tests/conftest.py`)
- `database_url` — a throwaway Postgres (pgserver, or `TEST_DATABASE_URL` if set), migrated
  to head once per session. It sets `DATABASE_URL` before the app is imported.
- `db` — a `Session`; every table is truncated after the test.
- `client` — `TestClient(create_app())`. It has **no** auth; once SPEC 2.1 exists, add an
  `auth_client` fixture in conftest (a `TestClient` with
  `headers={"Authorization": "Basic " + base64 of "team:dev-password"}`; TestClient has no
  `auth=` argument) and use it for every protected route.
Add fixtures to `conftest.py` when several tests need them; keep it readable.

## Required
- **Values, not truthiness**: `assert r.status_code == 201 and r.json()["title"] == "Demo"`.
- **One success and one failure path** per route or function.
- **Side effects**: after a POST, query the DB; after a refused request, assert nothing was
  stored (row count unchanged).
- **Real Postgres** for anything that stores data. Never mock the database.
- **No network**: Teams, the LLM and the waker are always faked with
  `httpx.MockTransport`. Assert what was sent (URL path, JSON body, headers) and how the
  code reacts to 202, 429, 500, timeouts and bad JSON.
- **No sleeping, no real clock**: pass `now` explicitly. Use fixed dates:
  `datetime(2026, 11, 16, 7, 30, tzinfo=UTC)` (a Monday, 08:30 in Amsterdam).
  DST tests: summer `datetime(2026, 6, 15, 6, 30, tzinfo=UTC)` = 08:30 local; the switch
  days 2026-03-29 and 2026-10-25.
- **Boundaries**: title of 200 vs 201 chars, the 6-hour window edge, 5 attempts, 3 job
  attempts, the 30-minute stuck limit, the 28 KB cap, upload size limit + 1 byte.

## Banned (these count as not-done)
- Tests with no assertion, `assert True`, or only "does not raise".
- Asserting that a mock was called instead of the observable result.
- `skip`/`xfail` to get green, or lowering the coverage limit.
- Tests that pass on today's date only. Never `date.today()` or `datetime.now()` in a test.
- Copying or editing the root `tests/fixtures/` files; read them in place.

## Shape
Arrange–Act–Assert, one behaviour per test, descriptive names
(`test_deadline_reminder_not_sent_twice`). The whole suite stays well under 2 minutes.

## Example
```python
def test_send_once_records_sent_and_skips_second_call(db):
    calls = []
    def handler(req):
        calls.append(json.loads(req.content))
        return httpx.Response(202)
    teams_client = httpx.Client(transport=httpx.MockTransport(handler))
    assert send_once(db, "test", "test:1", test_card(), client=teams_client) == "sent"
    assert send_once(db, "test", "test:1", test_card(), client=teams_client) == "skipped"
    assert len(calls) == 1
    assert calls[0]["attachments"][0]["contentType"] == "application/vnd.microsoft.card.adaptive"
    row = db.scalars(select(PostLog).where(PostLog.ref_key == "test:1")).one()
    assert (row.status, row.attempts) == ("sent", 1)
```

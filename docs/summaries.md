# Meeting summaries

Upload → parse in memory → `job` row `queued` → worker waits for the model → summary JSON
→ transcript deleted → posted to Teams (or a button). The model runs on a PC that sleeps
and can be paused by its owner, so a job may wait hours. That is fine; never time out a
queued job.

## Transcripts (`transcripts.py`)
`Turn(speaker: str, text: str)`. Human-owned samples: `tests/fixtures/sample.vtt` and
`tests/fixtures/sample.docx` (11 turns, 4 speakers; SPEC 7.2). Read them with a path from
`Path(__file__)`; never copy them into `backend/tests/` (they are the human's truth).
- **VTT (Teams)**: skip `WEBVTT`, blank lines, cue ids and `-->` timing lines. Speaker from
  `<v Name>…</v>`; a cue may span lines until `</v>`. Strip any other tags. Join
  consecutive cues of the same speaker into one turn. A cue without `<v>` gets speaker
  `"Onbekend"`.
- **DOCX (Teams download)**: open with `zipfile`, read only `word/document.xml`, parse with
  `defusedxml.ElementTree`. Paragraph text = all `w:t` in a `w:p`. A paragraph matching
  `^(?P<speaker>.+?)\s+(\d+:)?\d{1,2}:\d{2}$` starts a turn; the next non-empty paragraphs
  are its text. Paragraphs before the first speaker line (title, date, length) are skipped.
  Refuse zips whose `document.xml` is over 20 MB uncompressed (zip bomb guard).
- Bad input raises `TranscriptError` with a Dutch message; the route turns it into 422.
- `as_text(turns)` = `"Speaker: text"` lines; that is what `job.transcript` stores.

## LLM client (`llm.py`)
OpenAI-compatible llama-server, alias `LLM_MODEL` (`coder`), `Authorization: Bearer
LLM_API_KEY`. `is_up(client) -> bool`: `GET {LLM_BASE_URL}/models`, 5 s timeout.
`chat_json(messages, schema, client) -> dict`: `POST {LLM_BASE_URL}/chat/completions` with
```json
{"model": "coder", "messages": [...], "temperature": 0.2, "max_tokens": 4096,
 "chat_template_kwargs": {"enable_thinking": false},
 "response_format": {"type": "json_schema",
                     "json_schema": {"name": "meeting_summary", "schema": {...}}}}
```
Timeout `LLM_TIMEOUT_S`. Parse `choices[0].message.content` as JSON and validate it with a
pydantic model; raise `LlmError` on HTTP errors, bad JSON or a wrong shape. Never log the
prompt, the transcript or the key. Tests use `httpx.MockTransport` returning canned
completions.

## Summarising (`summarize.py`)
- System prompt (Dutch): you are the note-taker of a student scrum team; summarise in
  Dutch; list only decisions that were actually made; action items with owner and due date
  only when said; open questions; do not invent names or dates. User message: meeting
  title, date and the transcript text.
- Context is 48k tokens. When the transcript is longer than `SUMMARY_CHUNK_CHARS`, split it
  at turn (line) boundaries into parts below that size, summarise each, then send one merge
  call with the partial JSON results, asking for a single result in the same schema.
- Invalid output: retry the same call once, then raise.

## Worker (`worker.py`)
`run_once(session, now, llm_client, teams_client) -> str` does one step and returns what
happened (`"idle"`, `"model_offline"`, `"done"`, `"retry"`, `"failed"`), so tests drive it
step by step. `main()` loops: `run_once`, then sleep 60 s after `idle`/`model_offline`, no
sleep after work. On start, reset jobs `running` for > 30 min to `queued` (SPEC 7.7).
- Claim: `select(Job).where(status == "queued").order_by(created_at).limit(1)
  .with_for_update(skip_locked=True)`, set `running`, `started_at`, `attempts += 1`, commit.
- Success: store `result`, set `transcript = None`, `done`, `finished_at`; then if
  auto-post is on, `send_once(kind="summary", ref_key=f"summary:{id}")` and set `posted_at`.
- Failure: back to `queued` with `error`; at 3 attempts `failed`.
- Model state: store `{"up": bool, "checked_at", "last_up_at"}` in `app_state` key
  `model_status`; `/meetings` reads it.
- Wake (SPEC 7.9): store `last_wake` in `app_state`; send at most every 30 min; ignore
  errors from the waker (log the status code only).

## Summary card
Title "Samenvatting: <title> (<datum>)", then sections "Samenvatting" (text), "Besluiten"
(bullets), "Actiepunten" (FactSet: owner or "—" → task + due), "Open vragen", and the footer
line from SPEC 7.8 in a small, subtle TextBlock.

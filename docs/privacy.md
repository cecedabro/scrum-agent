# Privacy

The team agreed to use this tool. Everything runs on Cédric's own hardware (a k3s homelab
and a PC at home); no external AI service sees any data. The only data that leaves is what
is posted to the team's own Teams channel.

## What is stored, and for how long
| Data | Where | Kept |
| --- | --- | --- |
| Deadlines (title, date, time, note) | Postgres on the homelab | until 60 days after the deadline (`DEADLINE_RETENTION_DAYS`) |
| Reminder settings | Postgres | until changed |
| Uploaded transcript file | nowhere: parsed in memory, never written to disk | — |
| Transcript text (speaker names + what they said) | Postgres, `job.transcript` | until the summary is made; a failed job's text 7 days |
| Meeting summary (decisions, action items with names) | Postgres, `job.result` | 180 days (`SUMMARY_RETENTION_DAYS`) |
| Post log (what was posted when; no message text) | Postgres | 180 days (`POST_LOG_RETENTION_DAYS`) |
| Posts in Teams | Microsoft Teams (the school's tenant) | Teams' own rules; delete a post in Teams |

The model (`coder`, llama-server on the PC) receives the transcript text while it makes a
summary and keeps nothing afterwards. App logs contain no transcript text, summaries,
passwords or the webhook URL; the cluster keeps logs only as long as the pods exist.

## Who can see it
Anyone with the team password (the web page) and the members of the Teams channel (the
posts). The repo is public but contains no team data: no names, no transcripts, no secrets.
The sample transcripts in `tests/fixtures/` are made up.

## How to delete
- One meeting or deadline: its delete button on the web page (immediate).
- Everything: `kubectl --context homelab -n scrum-agent exec scrum-agent-db-0 -- psql -U
  scrum -d scrum -c 'TRUNCATE job, deadline, post_log, app_state;'`.
- The whole app: remove `apps/scrum-agent` from the homelab repo, then
  `kubectl --context homelab delete ns scrum-agent` (deletes the database volume too).
- Database backups: the homelab's Longhorn backups follow their own schedule; deleted rows
  disappear from them once the oldest backup that still has them expires.

A teammate who wants their data removed asks Cédric, who deletes the matching meetings.

# scrum-agent

A small self-hosted assistant for our school scrum team. It:

- keeps a **deadlines list** on a web page;
- posts **reminders** to our Microsoft Teams channel (Monday overview, 2 days and 1 day
  before each deadline, optional "sprint ends" nudge), on a schedule, without AI;
- turns an uploaded Teams **meeting transcript** (`.vtt` or `.docx`) into a Dutch summary
  with decisions and action items, made by a local model on my own PC, and posts it.

Everything runs on my own hardware (a k3s homelab and a PC). See
[docs/privacy.md](docs/privacy.md) for what is stored and how to delete it.

Built mostly by a local coding agent working through [PLAN.md](PLAN.md) against
[SPEC.md](SPEC.md); the rules for it are in [AGENTS.md](AGENTS.md).

## Develop
```bash
make setup   # uv sync
make check   # lint, types, tests, security scan
make dev     # the site on http://localhost:8000 with fake data (login: team / dev-password)
```

## Setup (one time, by Cédric)

### 1. The Teams webhook
In Teams, in the team's channel: **⋯ → Workflows → "Post to a channel when a webhook
request is received"** (or "Send webhook alerts to a channel"), pick the team and channel,
save, and copy the URL. Do not paste it anywhere except step 2. Tip: add a teammate as
co-owner of the flow, so it keeps working if your account loses access.

### 2. Secrets into OpenBao
From the repo on the Mac (asks for your OpenBao token, the webhook URL and a team password;
shows none of them):
```bash
scripts/store-secrets.sh init
```
It writes `secret/scrum-agent/app` (`TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`, `LLM_API_KEY`,
copied from the devbox secret) and `secret/scrum-agent/db`. Later, to replace only the
webhook: `scripts/store-secrets.sh webhook`. Share the team password with teammates in a
private Teams chat, not in the channel.

### 3. `@Agent` in Teams (phase 3, after T42 and once the site is online)
A team owner: team **⋯ → Manage team → Apps → "Create an outgoing webhook"**. Name `Agent`,
callback URL `https://scrum.cedricschippers.dev/teams/outgoing`. Teams shows a security token
once: don't paste it anywhere except here:
```bash
scripts/store-secrets.sh hmac
```
Then `@Agent wat zijn de deadlines?` in a channel of that team. If you put Cloudflare Access
in front of the site, add a bypass for the path `/teams/outgoing` (Teams can't log in; the
HMAC check protects that path).

### 4. Cluster and hostname (after the `deploy/` tasks are done)
The homelab chat copies `deploy/` into `~/homelab/apps/scrum-agent/` and adds the
ExternalSecrets and the NetworkPolicy. Then add `scrum.cedricschippers.dev` → Service
`scrum-agent.scrum-agent:80` in the Cloudflare tunnel. Optional extra lock: a Cloudflare
Access policy (email one-time PIN for the team's addresses) in front of the password.

## Let the local agent build it
One time: add `cecedabro/scrum-agent` to the devbox's fine-grained GitHub token
(Contents, Pull requests: read/write; Actions: read; Workflows: read/write for T34).
Then on the devbox (`ssh agent@devbox`):
```bash
git clone https://github.com/cecedabro/scrum-agent ~/repos/scrum-agent
cd ~/repos/scrum-agent && make setup && make check
python3 ~/harness-dev/loop.py      # works through PLAN.md on a new agent/… branch, opens a PR
```
Stop after the current task: `touch .agent/STOP`. Fix failures on main automatically:
`python3 ~/harness-dev/watch.py` in another tmux window.

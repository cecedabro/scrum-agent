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
It writes `secret/scrum-agent/app` (`TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`, an empty
`TEAMS_HMAC_SECRET`) and `secret/scrum-agent/db`. The model API key and the waker token are
read straight from the ai-agent secrets by the cluster. Later, to replace only the
webhook: `scripts/store-secrets.sh webhook`. Share the team password with teammates in a
private Teams chat, not in the channel.

### 3. `@Agent` in Teams (phase 3, after T50 and once the site is online)
A team owner: team **⋯ → Manage team → Apps → "Create an outgoing webhook"**. Name `Agent`,
callback URL `https://scrum.cedricschippers.dev/teams/outgoing`. Teams shows a security token
once: don't paste it anywhere except here:
```bash
scripts/store-secrets.sh hmac
```
Then `@Agent wat zijn de deadlines?` in a channel of that team. Don't put Cloudflare Access
in front of `/teams/outgoing` (Teams can't log in; the HMAC check protects that path).

### 4. Cluster and hostname
1. The homelab chat copies `deploy/` into `~/homelab/apps/scrum-agent/` and adds the Flux
   image automation and the NetworkPolicy (after your OK).
2. After the first release (merge to `main`): GitHub → your profile → Packages →
   `scrum-agent` → Package settings → Change visibility → **Public** (the cluster pulls
   without credentials).
3. Cloudflare dashboard → Zero Trust → Networks → Tunnels → your tunnel → Public hostname:
   `scrum.cedricschippers.dev` → `http://scrum-agent.scrum-agent.svc.cluster.local:80`.

## Let the local agent build it
One time: add `cecedabro/scrum-agent` to the devbox's fine-grained GitHub token
(Contents, Pull requests: read/write; Actions: read; Workflows: read/write for T42).
Then on the devbox (`ssh agent@devbox`):
```bash
git clone https://github.com/cecedabro/scrum-agent ~/repos/scrum-agent
cd ~/repos/scrum-agent && make setup && make check
python3 ~/harness-dev/loop.py      # works through PLAN.md on a new agent/… branch, opens a PR
```
Stop after the current task: `touch .agent/STOP`. Fix failures on main automatically:
`python3 ~/harness-dev/watch.py` in another tmux window.

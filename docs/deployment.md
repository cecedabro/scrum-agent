# Deployment (k3s homelab)

The app runs on Cédric's k3s cluster, deployed by Flux from the **homelab** repo. This repo
builds the image and keeps *draft* manifests in `deploy/`; the homelab side copies them into
`homelab/apps/scrum-agent/` and adds the NetworkPolicy and ExternalSecrets. You never touch
the cluster or the homelab repo.

## How a change reaches the cluster
1. A PR is merged into `main`.
2. `.github/workflows/release.yml` runs `make check` and the migration check, computes the
   next version (`backend/scripts/next_version.py`), builds and pushes
   `ghcr.io/cecedabro/scrum-agent:X.Y.Z` and `:sha-<short>`, then pushes the tag `vX.Y.Z`
   (all in one workflow: tags pushed with `GITHUB_TOKEN` trigger nothing).
3. Flux image automation sees `X.Y.Z` and rolls it out.

## The image
Already written (root `Dockerfile`): `backend/` → `/app`, venv in `/app/.venv`, uid 10001,
port 8000. The same image runs three ways: the web app (default `CMD`),
`python -m app.worker`, and `python -m app.tick`. Migrations: `alembic upgrade head` in an
initContainer of the web Deployment. Nothing may write outside `/tmp`. There is no Docker in
the devbox; `.github/workflows/image.yml` builds and smoke-tests it.

## Runtime facts (agreed with the homelab side, do not change)
| What | Value |
| --- | --- |
| Namespace | `scrum-agent` |
| Web | Deployment `scrum-agent`, 1 replica, `Recreate`, port 8000, Service `scrum-agent` port 80, liveness `/healthz`, readiness `/readyz` |
| Worker | Deployment `scrum-agent-worker`, 1 replica, `Recreate`, `command: ["python", "-m", "app.worker"]`, no Service, no probes |
| Tick | CronJob `scrum-agent-tick`, `*/10 * * * *`, `timeZone: Europe/Amsterdam`, `concurrencyPolicy: Forbid`, `startingDeadlineSeconds: 300`, `backoffLimit: 0`, keep 3 successful / 3 failed jobs |
| Env (Secret `scrum-agent-app`) | `DATABASE_URL`, `TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`, `LLM_API_KEY` (all three workloads use `envFrom`) |
| Env (plain) | `APP_ENV=production`, `LLM_BASE_URL=http://192.168.50.17:8080/v1`, `TEAM_USER=team` |
| DB | StatefulSet `scrum-agent-db`, `postgres:16.10`, Secret `scrum-agent-db` (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`), `PGDATA=/var/lib/postgresql/data/pgdata`, Service `scrum-agent-db:5432`, 2Gi `longhorn` PVC, fsGroup 999 |
| Resources | web 25m/128Mi request, 256Mi limit; worker 10m/96Mi, 192Mi; tick 10m/96Mi, 192Mi; Postgres 50m/256Mi, 512Mi |
| Security | runAsNonRoot, uid 10001, readOnlyRootFilesystem, drop ALL caps, seccomp RuntimeDefault, emptyDir on `/tmp`, `automountServiceAccountToken: false` |
| Placement | avoid node `k3s-gpu-01` (node affinity `NotIn`) |
| Public URL | `https://scrum.cedricschippers.dev` via the Cloudflare tunnel (no Ingress object) |

The worker needs egress to the PC (`192.168.50.17:8080`) and, if the waker is used,
`192.168.50.11:9009`; the web app and the tick need HTTPS egress to the Teams webhook. That
is the homelab NetworkPolicy's job; just list it in `deploy/README.md`.

## Layout (inside `deploy/`)
```
deploy/
  Makefile             # validate: kustomize build . | kubeconform -strict -summary
  kustomization.yaml   # namespace: scrum-agent; lists the files below
  namespace.yaml
  app.yaml             # web Deployment (initContainers: wait-for-db, migrate) + Service
  worker.yaml          # worker Deployment
  tick.yaml            # CronJob
  postgres.yaml        # StatefulSet + Service + volumeClaimTemplate
  secret.example.yaml  # both Secrets with REPLACE_ME values; NOT in the kustomization
  README.md            # egress needs, secret paths, how to roll back
```
Image lines: `ghcr.io/cecedabro/scrum-agent:0.1.0 # {"$imagepolicy": "flux-system:scrum-agent"}`
in all three workloads. Validate with `make -C deploy validate`; lint workflows with
`uvx --from actionlint-py actionlint`.

## Migrations are auto-deployed
Every merge deploys with one replica and `Recreate`; a failing migration takes the site
down. So migrations are additive and idempotent, and `tests/ci/check-migrations.sh` (human
owned) must pass before a release.

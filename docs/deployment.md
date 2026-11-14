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
| Namespace | `scrum-agent`, Pod Security `restricted` (enforce + warn) |
| Web | Deployment `scrum-agent`, 1 replica, `Recreate`, port 8000, Service `scrum-agent` port 80, liveness `/healthz`, readiness `/readyz`; initContainers `wait-for-db` and `migrate` use the app image |
| Worker | Deployment `scrum-agent-worker`, 1 replica, `Recreate`, `command: ["python", "-m", "app.worker"]`, no Service, no probes |
| Tick | CronJob `scrum-agent-tick`, `*/10 * * * *`, `timeZone: Europe/Amsterdam`, `concurrencyPolicy: Forbid`, `startingDeadlineSeconds: 300`, `backoffLimit: 0`, `activeDeadlineSeconds: 240`, keep 1 successful / 3 failed jobs |
| Env (Secret `scrum-agent-app`, from ExternalSecret) | `DATABASE_URL` (composed from the db secret), `TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`, `TEAMS_HMAC_SECRET`, `LLM_API_KEY` (= OpenBao `ai-agent/devbox` `LLAMA_API_KEY`), `WAKER_TOKEN` (= `ai-agent/waker` `WAKER_TOKEN`) |
| Env (plain) | `APP_ENV=production`, `TEAM_USER=team`, `LLM_BASE_URL=http://192.168.50.17:8080/v1`, `LLM_MODEL=coder`, `WAKER_URL=http://192.168.50.11:9009` |
| DB | StatefulSet `scrum-agent-db`, `postgres:16.15-alpine3.24@sha256:…` (pinned by digest, Renovate bumps it), Secret `scrum-agent-db`, `PGDATA=/var/lib/postgresql/data/pgdata`, uid/fsGroup 999, emptyDir on `/var/run/postgresql`, Service `scrum-agent-db:5432`, 5Gi `longhorn` PVC (nightly Longhorn backup) |
| Resources (no CPU limits) | web 50m/96Mi, limit 256Mi; worker 50m/128Mi, 384Mi; tick 10m/64Mi, 128Mi; Postgres 100m/256Mi, 512Mi |
| Security | runAsNonRoot, uid 10001, readOnlyRootFilesystem, no privilege escalation, drop ALL caps, seccomp RuntimeDefault, emptyDir on `/tmp`, `automountServiceAccountToken: false` |
| Placement | preferred away from `k3s-gpu-01` and `k3s-worker-02` |
| Public URL | `https://scrum.cedricschippers.dev` via the Cloudflare tunnel (route set in the Cloudflare dashboard, no Ingress object, no Cloudflare Access) |
| Image | public GHCR package; Flux ImageRepository/ImagePolicy `flux-system/scrum-agent` (tags `vX.Y.Z`, semver `>=0.1.0`) rewrites every line with the marker |

The homelab adds a NetworkPolicy with default-deny egress: DNS, same namespace (Postgres),
`192.168.50.17:8080` (llama-server), `192.168.50.11:9009` (waker) and public TCP 443 (Teams).

## Layout (inside `deploy/`)
```
deploy/
  Makefile             # validate: kustomize build . | kubeconform -strict -ignore-missing-schemas
  kustomization.yaml   # only for validation here; the homelab lists the files itself
  namespace.yaml
  app.yaml             # web Deployment (initContainers: wait-for-db, migrate) + Service
  worker.yaml          # worker Deployment
  tick.yaml            # CronJob
  postgres.yaml        # StatefulSet + Service + volumeClaimTemplate
  externalsecret.yaml  # ExternalSecrets scrum-agent-app and scrum-agent-db (store `openbao`)
  README.md            # what the homelab copies, OpenBao keys, egress, rollback
```
Image lines: `ghcr.io/cecedabro/scrum-agent:v0.1.0 # {"$imagepolicy": "flux-system:scrum-agent"}`
on every container that runs the app image (web, wait-for-db, migrate, worker, tick).
Validate with `make -C deploy validate`; lint workflows with `uvx --from actionlint-py actionlint`.

## Migrations are auto-deployed
Every merge deploys with one replica and `Recreate`; a failing migration takes the site
down. So migrations are additive and idempotent, and `tests/ci/check-migrations.sh` (human
owned) must pass before a release.

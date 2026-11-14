# Deploy — scrum-agent

Kustomize manifests for the scrum-agent on a k3s homelab.

## Overview

The homelab copies the plain manifests into `apps/scrum-agent/` (one Flux GitRepository, the
homelab repo) and lists them in its `apps/kustomization.yaml`. `kustomization.yaml` and
`Makefile` here are only for `make validate`.

```
namespace.yaml       # Pod Security restricted
app.yaml             # web Deployment + Service scrum-agent:80 -> 8000
worker.yaml          # worker Deployment
tick.yaml            # CronJob every 10 min
postgres.yaml        # StatefulSet + Service + 5Gi longhorn PVC
externalsecret.yaml  # Secrets scrum-agent-app and scrum-agent-db from OpenBao
```

## Secrets (OpenBao, ClusterSecretStore `openbao`)

Filled by Cédric with `scripts/store-secrets.sh init`:
- `secret/scrum-agent/app`: `TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`, `TEAMS_HMAC_SECRET` (empty
  until `@Agent` is set up; empty = `/teams/outgoing` answers 503)
- `secret/scrum-agent/db`: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

Reused from the ai-agent secrets (not copied): `ai-agent/devbox` `LLAMA_API_KEY` → `LLM_API_KEY`,
`ai-agent/waker` `WAKER_TOKEN`. `DATABASE_URL` is composed in the ExternalSecret template.

## Egress needs

Default-deny egress, then: DNS; same namespace (Postgres 5432); `192.168.50.17:8080`
(llama-server, worker); `192.168.50.11:9009` (waker, worker); public TCP 443 (Teams webhook,
web + worker + tick). Ingress: only the Cloudflare tunnel to the web pod.

## Manual steps (Cédric)

1. `scripts/store-secrets.sh init` (OpenBao).
2. After the first release: make the GHCR package `scrum-agent` public.
3. Cloudflare dashboard: tunnel route `scrum.cedricschippers.dev` →
   `http://scrum-agent.scrum-agent.svc.cluster.local:80`. No Cloudflare Access in front of
   `/teams/outgoing`.

## Rollback

The web Deployment uses `Recreate` with 1 replica. To roll back to a previous image:

```bash
kubectl -n scrum-agent rollout undo deployment/scrum-agent
```

The worker and tick have no rollout history (CronJob / Deployment without rolling update).
If the worker is running a bad image, delete its pods and let the Deployment recreate them
with the previous image tag. The tick will pick up the new image on its next scheduled run.

Migrations are run as an initContainer on web start, so a rollback that reverts the image
must also revert the database migration version (see `PLAN.md` for migration rules).

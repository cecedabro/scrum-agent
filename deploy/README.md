# Deploy — scrum-agent

Kustomize manifests for the scrum-agent on a k3s homelab.

## Overview

```
deploy/
  Makefile             # validate: kustomize build . | kubeconform -strict -summary
  kustomization.yaml   # namespace: scrum-agent; lists namespace.yaml and app.yaml
  namespace.yaml
  app.yaml             # web Deployment + Service
  worker.yaml          # worker Deployment
  tick.yaml            # CronJob (every 10 min)
  postgres.yaml        # StatefulSet + Service + PVC
  secret.example.yaml  # Secret templates with REPLACE_ME values (not in kustomization)
  README.md            # this file
```

## Secrets

Both Secrets are **not** in the kustomization. In production they are created by the homelab
side (OpenBao + ExternalSecrets). The OpenBao paths are:

- `secret/scrum-agent/app` — keys: `DATABASE_URL`, `TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`,
  `LLM_API_KEY`, `TEAMS_HMAC_SECRET`
- `secret/scrum-agent/db` — keys: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

See `secret.example.yaml` for the full key list with placeholder values.

## Egress needs

The homelab NetworkPolicy must allow outbound traffic from the `scrum-agent` namespace:

- **Worker** → `192.168.50.17:8080` (llama-server / local PC)
- **Worker** → `192.168.50.11:9009` (waker, when `WAKER_URL` / `WAKER_TOKEN` are set)
- **Web + Tick** → the Teams webhook URL (`https://` only; the URL is in `TEAMS_WEBHOOK_URL`)

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

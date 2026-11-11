#!/usr/bin/env bash
# Store the scrum agent's secrets in OpenBao (KV v2 engine `secret`), from your Mac.
# Human-run; the agent may not edit it. Nothing is echoed: values are read with
# `read -s`, sent to OpenBao on stdin, and never put on a command line or printed.
#
#   scripts/store-secrets.sh init           # first time: app + db secrets
#   scripts/store-secrets.sh webhook        # replace only TEAMS_WEBHOOK_URL
#   scripts/store-secrets.sh team-password  # replace only TEAM_PASSWORD
#
# Paths: secret/scrum-agent/app  TEAM_PASSWORD, TEAMS_WEBHOOK_URL, LLM_API_KEY
#        secret/scrum-agent/db   POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
set -euo pipefail

BAO_ADDR=${BAO_ADDR:-https://openbao.home.cedricschippers.dev}
APP=scrum-agent/app
DB=scrum-agent/db

ask_secret() {  # ask_secret VAR "prompt": read a value without echo
  local __v
  read -rsp "$2: " __v
  echo
  printf -v "$1" '%s' "$__v"
}

auth() { printf 'X-Vault-Token: %s\n' "$BAO_TOKEN"; }

get_json() {  # get_json PATH: the secret's JSON on stdout; exit 1 if it does not exist
  curl -fsS -H @<(auth) "$BAO_ADDR/v1/secret/data/$1"
}

exists() { get_json "$1" >/dev/null 2>&1; }

field() {  # field PATH KEY: one value on stdout (captured by the caller, never shown)
  get_json "$1" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["data"][sys.argv[1]])' "$2"
}

# write METHOD PATH KEY...: values arrive on stdin, one per line, in the same order.
# POST replaces the whole secret; PATCH merges keys into an existing one.
write() {
  local method=$1 path=$2 ctype=application/json
  shift 2
  [ "$method" = PATCH ] && ctype=application/merge-patch+json
  python3 -c 'import json,sys; v=sys.stdin.read().split("\n"); print(json.dumps({"data": dict(zip(sys.argv[1:], v))}))' "$@" \
    | curl -fsS -o /dev/null -X "$method" -H @<(auth) -H "Content-Type: $ctype" \
        --data-binary @- "$BAO_ADDR/v1/secret/data/$path"
  echo "stored: secret/$path ($*)"
}

ask_webhook() {
  ask_secret WEBHOOK "Teams Workflows webhook URL (paste, not shown)"
  case "$WEBHOOK" in
    https://*) ;;
    *) echo "that does not look like an https:// URL; nothing stored" >&2; exit 1 ;;
  esac
}

ask_team_password() {
  ask_secret TEAM_PW "Team password for the web page (empty = generate one)"
  if [ -z "$TEAM_PW" ]; then
    TEAM_PW=$(openssl rand -base64 24 | tr -d '/+=')
    echo "generated a team password: read it in the OpenBao UI at secret/$APP"
  fi
  if [ "${#TEAM_PW}" -lt 12 ]; then
    echo "the team password needs at least 12 characters; nothing stored" >&2; exit 1
  fi
}

cmd=${1:-}
case "$cmd" in init|webhook|team-password) ;; *) sed -n '2,11p' "$0"; exit 2 ;; esac

ask_secret BAO_TOKEN "OpenBao token (not shown)"

case "$cmd" in
  init)
    if exists "$DB"; then
      echo "secret/$DB exists: kept (changing it would not change the real DB password)"
    else
      printf '%s\n%s\n%s' scrum scrum "$(openssl rand -hex 24)" \
        | write POST "$DB" POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD
    fi
    ask_team_password
    ask_webhook
    LLM_KEY=$(field ai-agent/devbox LLAMA_API_KEY)  # same llama-server key as the devbox
    printf '%s\n%s\n%s' "$TEAM_PW" "$WEBHOOK" "$LLM_KEY" \
      | write POST "$APP" TEAM_PASSWORD TEAMS_WEBHOOK_URL LLM_API_KEY
    ;;
  webhook)
    ask_webhook
    printf '%s' "$WEBHOOK" | write PATCH "$APP" TEAMS_WEBHOOK_URL
    ;;
  team-password)
    ask_team_password
    printf '%s' "$TEAM_PW" | write PATCH "$APP" TEAM_PASSWORD
    ;;
esac

unset BAO_TOKEN WEBHOOK TEAM_PW LLM_KEY
cat <<'EOF'
Done. Once the app runs on the cluster, make it pick up the change now:
  kubectl --context homelab -n scrum-agent annotate externalsecret scrum-agent-app force-sync=$(date +%s) --overwrite
  kubectl --context homelab -n scrum-agent rollout restart deploy/scrum-agent deploy/scrum-agent-worker
EOF

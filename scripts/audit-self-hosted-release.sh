#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
HAS_GIT_WORKTREE=0
if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  HAS_GIT_WORKTREE=1
fi

fail() {
  printf 'self-hosted release audit failed: %s\n' "$1" >&2
  exit 1
}

require() {
  grep -Fq "$2" "$1" || fail "expected $2 in $1"
}

printf '%s\n' '== Repository boundary =='
if [[ "$HAS_GIT_WORKTREE" == "1" ]]; then
  git ls-files --error-unmatch .env .env.compose .env.license-control >/dev/null 2>&1 \
    && fail 'a local environment file is tracked' || true
  git check-ignore -q .env.license-control || fail '.env.license-control must be ignored'
  git check-ignore -q .env.customer || fail '.env.customer must be ignored'
elif [[ -e .env || -e .env.compose || -e .env.license-control ]]; then
  fail 'a source archive contains a local environment file'
fi

printf '%s\n' '== Tracked secret scan =='
credential_pattern='s''k-[A-Za-z0-9]{20,}|BEGIN (RSA |EC |OPENSSH )?PRIVATE'' KEY|AKIA[0-9A-Z]{16}'
if [[ "$HAS_GIT_WORKTREE" == "1" ]]; then
  if git grep -nE "$credential_pattern" -- . >/dev/null; then
    fail 'a likely credential or private key was found in tracked files'
  fi
elif grep -R -n -E --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist \
  --exclude-dir=.venv \
  "$credential_pattern" . >/dev/null; then
  fail 'a likely credential or private key was found in the source archive'
fi

printf '%s\n' '== Compose boundary =='
if [[ -f SELF_HOSTED_SOURCE_REVISION ]]; then
  for forbidden in \
    'BILLING_STRIPE_WEBHOOK_SECRET' \
    'BILLING_PRICING_CATALOG_PATH' \
    'HOSTED_DEFAULT_PLAN_ID' \
    'SYSTEM_LLM_API_KEY' \
    'AI_PROCESS_API' \
    'DEEPSEEK_API_KEY'; do
    if grep -Eq "^[[:space:]]*${forbidden}:" compose.yml; then
      fail "hosted setting $forbidden is present in compose.yml"
    fi
  done
  require compose.yml 'LLM_SYSTEM_FALLBACK_ENABLED: "false"'
  require compose.yml './config/licensing:/app/config/licensing:ro'
  COMPOSE_ARGS=(compose.yml)
else
  for expected in \
    'AI_PROCESS_API: ""' \
    'DEEPSEEK_API_KEY: ""' \
    'BILLING_STRIPE_WEBHOOK_SECRET: ""' \
    'SYSTEM_LLM_API_KEY: ""' \
    'LLM_SYSTEM_FALLBACK_ENABLED: "false"' \
    'E2E_RUNTIME_ENABLED: "false"'; do
    require compose.self-hosted.yml "$expected"
  done
  require compose.self-hosted.yml './config/licensing:/app/config/licensing:ro'
  COMPOSE_ARGS=(compose.yml compose.self-hosted.yml)
fi

POSTGRES_PASSWORD=release-audit-password \
AUTH_SECRET_KEY=release-audit-auth-secret-at-least-32 \
LLM_CREDENTIAL_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA \
bash -c '
  set -euo pipefail
  command=(docker compose)
  for compose_file in "$@"; do
    command+=(-f "$compose_file")
  done
  command+=(--env-file .env.self-hosted.example config --quiet)
  "${command[@]}"
' -- "${COMPOSE_ARGS[@]}"

printf '%s\n' '== Public package inventory =='
test -f 03_delivery/self-hosted-public-manifest.md || fail 'public manifest is missing'
test -f SECURITY.md || fail 'security policy is missing'
test -f 03_delivery/self-hosted-installation.md || fail 'installation guide is missing'
if [[ -f SELF_HOSTED_SOURCE_REVISION ]]; then
  test ! -e apps/license_control_plane || fail 'issuer service must be absent from public package'
  test ! -e apps/api/src/process_architect_api/hosted || fail 'hosted billing package must be absent from public package'
  test ! -e apps/api/src/process_architect_api/admin_routes.py || fail 'hosted admin routes must be absent from public package'
  test ! -e config/billing-pricing || fail 'hosted pricing catalog must be absent from public package'
fi

printf '%s\n' 'self-hosted-release-audit=ok'

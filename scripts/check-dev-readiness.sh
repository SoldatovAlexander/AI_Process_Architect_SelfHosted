#!/bin/sh
set -eu

base_url="${1:-http://127.0.0.1:5173}"
api_url="${API_URL:-http://127.0.0.1:8000}"

health_payload=$(curl -fsS "$api_url/health")
printf '%s' "$health_payload" | grep -F '"rubric":{"status":"ready"' >/dev/null
curl -fsS "$base_url" >/dev/null

printf '%s\n' "dev-readiness=ok"

#!/bin/sh
set -eu

if [ -z "${GRAFANA_ADMIN_PASSWORD:-}" ]; then
  echo "GRAFANA_ADMIN_PASSWORD must be set in .env.compose" >&2
  exit 1
fi

export GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_ADMIN_PASSWORD"
exec /run.sh

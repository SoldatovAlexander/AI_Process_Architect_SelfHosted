#!/usr/bin/env sh
set -eu

if [ "${MIGRATE_ON_START:-1}" = "1" ]; then
  alembic -c /app/apps/api/alembic.ini upgrade head
fi
exec "$@"

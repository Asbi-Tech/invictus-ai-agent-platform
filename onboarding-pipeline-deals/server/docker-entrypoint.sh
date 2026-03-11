#!/bin/sh
set -e

# Run migrations only if RUN_MIGRATIONS=true (used by CI/CD migration jobs)
if [ "$RUN_MIGRATIONS" = "true" ]; then
  echo "==> Running Alembic migrations..."
  alembic upgrade head
  echo "==> Migrations complete."
  exit 0
fi

echo "==> Starting Invictus Deals Onboarding API..."
exec python start_server.py

#!/bin/sh
set -e

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Starting Invictus Deals Onboarding API..."
exec python start_server.py

#!/usr/bin/env bash
set -euo pipefail

export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-dev-only-secret-not-for-production}"
export DJANGO_DEBUG=True
export DATABASE_URL="${DATABASE_URL:-postgres://envbooker:envbooker@localhost:5432/envbooker}"

docker compose up -d

uv run python manage.py migrate --run-syncdb

exec uv run python manage.py runserver

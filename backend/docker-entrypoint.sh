#!/bin/sh
set -eu

echo "▶ Running database migrations..."
alembic upgrade head

echo "▶ Loading public dataset..."
python scripts/seed_public.py

echo "▶ Starting Happy Hour AI API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

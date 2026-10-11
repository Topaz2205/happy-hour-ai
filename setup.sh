#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "Happy Hour AI — Setup"
echo "====================="

if ! command -v docker >/dev/null 2>&1; then
  echo "❌ Docker is required."
  echo "Install Docker Desktop and run this script again."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "❌ Docker Desktop is installed but not running."
  exit 1
fi

if [ ! -f backend/.env ]; then
  cp .env.example backend/.env
  echo "✅ Created backend/.env from .env.example"
  echo "ℹ️  Add an LLM_API_KEY to backend/.env to enable AI guidance."
fi

echo
echo "▶ Building and starting Happy Hour AI..."
docker compose up --build -d

echo
echo "▶ Waiting for services..."
sleep 8

echo
docker compose ps

echo
echo "✅ Happy Hour AI is running"
echo "Frontend: http://localhost:3000"
echo "API docs: http://localhost:8000/docs"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "Happy Hour AI — Rebuild"
echo "======================="

docker compose up --build -d

echo
echo "▶ Waiting for services..."
sleep 8

echo
docker compose ps

echo
echo "▶ API health:"
curl -s http://localhost:8000/api/health || true
echo

echo
echo "✅ Rebuild complete"

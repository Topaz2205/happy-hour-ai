#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "Happy Hour AI — Reset"
echo "====================="
echo
echo "This removes the Docker database volume and rebuilds"
echo "the public database from public_seed.json."
echo

docker compose down -v --remove-orphans
docker compose up --build -d

echo
echo "▶ Waiting for services..."
sleep 8

docker compose ps

echo
echo "✅ Public database rebuilt"
echo "Frontend: http://localhost:3000"

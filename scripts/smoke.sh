#!/usr/bin/env bash
set -euo pipefail

BACKEND_URL=${BACKEND_URL:-http://localhost:8001}

echo "Waiting for backend health..."
for i in {1..30}; do
  if curl -sf "${BACKEND_URL}/api/v1/health" >/dev/null; then
    echo "Backend is healthy"
    break
  fi
  sleep 1
done

echo "Fetching config..."
curl -sf "${BACKEND_URL}/api/v1/config" || { echo "Config fetch failed"; exit 1; }
echo "Smoke test passed."

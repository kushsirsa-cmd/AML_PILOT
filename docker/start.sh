#!/bin/sh
# Starts the API (127.0.0.1:8000), waits until it has migrated + seeded, then serves the UI on $PORT.
set -e
cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API=$!
echo "[start] waiting for API (first boot seeds 100 customers / 50 businesses / 500 transactions)…"
i=0
until python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')" 2>/dev/null; do
  i=$((i+1)); [ $i -gt 120 ] && echo "[start] API failed to start" && exit 1
  kill -0 $API 2>/dev/null || { echo "[start] API exited"; exit 1; }
  sleep 1
done
echo "[start] API ready — serving UI on :${PORT:-8080}"
cd /app/web
exec node server.js

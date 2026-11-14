#!/usr/bin/env bash
# One-command setup & start.   ./setup.sh          → Docker (recommended)
#                              ./setup.sh --local  → no Docker: Python venv + npm, SQLite
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
if [ "${1:-}" = "--local" ]; then
  command -v python3 >/dev/null || { echo "python3 required"; exit 1; }
  command -v npm >/dev/null || { echo "node/npm required"; exit 1; }
  python3 -m venv .venv && . .venv/bin/activate
  pip install -q -r backend/requirements.txt
  (cd frontend && npm install --no-audit --no-fund --silent && BACKEND_URL=http://127.0.0.1:8000 npm run build >/dev/null)
  export DATABASE_URL=sqlite:///$PWD/demo.db
  (cd backend && uvicorn app.main:app --port 8000 &) ; sleep 2
  echo; echo "==> Open http://localhost:3000  (first start seeds the demo data, ~15s)"
  cd frontend && exec npm run start
fi
command -v docker >/dev/null || { echo "Docker not found. Install Docker Desktop, or run: ./setup.sh --local"; exit 1; }
docker compose up --build -d
echo "Waiting for the app…"
for i in $(seq 1 90); do curl -fs http://localhost:3000/api/health >/dev/null 2>&1 && break; sleep 2; done
echo; echo "==> AML Copilot is running:  http://localhost:3000"
echo "    Sign in with any persona — password: ${DEMO_PASSWORD:-demo1234}   (analyst.demo, senior.demo, mlro.demo, manager.demo, admin.demo)"
echo "    Logs: docker compose logs -f   |   Stop: docker compose down"

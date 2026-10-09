#!/usr/bin/env bash
# One command without Docker (macOS / Linux):   ./scripts/start.sh   → http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PORT:-8000}"
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  for c in python3.12 python3.13 python3.11 python3; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
fi
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install -q --disable-pip-version-check -r backend/requirements.txt
if [ ! -f frontend/dist/index.html ]; then
  (cd frontend && npm ci --no-audit --no-fund && npm run build)
fi
echo "Maru Takeoff & Quoting Assistant → http://localhost:$PORT  (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$PORT"

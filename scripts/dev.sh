#!/usr/bin/env bash
# Developer launcher for macOS/Linux: starts the FastAPI backend and the Vite
# dev server (which proxies /api and /ws to the backend). Windows users should
# use installer/install.ps1 for the packaged desktop app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${AIBENCH_PORT:-8760}"

cd "$ROOT/backend"
python3 -m pip install -q -r requirements.txt
echo "Starting backend on http://127.0.0.1:${BACKEND_PORT} ..."
python3 -m uvicorn aibench.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

cd "$ROOT/frontend"
[ -d node_modules ] || npm install
echo "Starting web UI (dev) ..."
npm run dev

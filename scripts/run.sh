#!/usr/bin/env bash
# Start ConsentLens. Run from Terminal.app so macOS grants Camera/Mic to Terminal.
# --dev: auto-reload on code changes + MANUAL_TEST protect button + local diagnostic original.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--dev" ]]; then
  export ENABLE_DEV_CONTROLS=true ENABLE_DIAGNOSTIC_ORIGINAL=true
  exec .venv/bin/python -m uvicorn backend.app.main:app --port 8000 --reload \
    --reload-dir backend --reload-dir shared --reload-dir frontend
fi
if [[ "${1:-}" == "--lan" ]]; then
  # For the companion app on a phone: listens on the network. Only the token-protected
  # /api/ingest socket is reachable from other devices; everything else is local-only.
  grep -q '^INGEST_TOKEN=..*' .env || { echo "Set INGEST_TOKEN in .env first"; exit 1; }
  exec .venv/bin/python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
fi
exec .venv/bin/python -m uvicorn backend.app.main:app --port 8000

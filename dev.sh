#!/usr/bin/env bash
# Run the backend (REST API + reviewer MCP) on :8000 and the frontend on :3000 together.
# Press Ctrl-C to stop both. Run ./setup.sh first.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Starting backend on http://localhost:8000 (REST + /mcp)…"
( cd app/backend && uv run uvicorn claims.api.app:app --port 8000 ) &
BACKEND_PID=$!

cleanup() { kill "$BACKEND_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> Starting frontend on http://localhost:3000…"
( cd app/frontend && npm run dev )

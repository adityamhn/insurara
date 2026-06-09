#!/usr/bin/env bash
# One-command setup: backend deps + seeded demo DB + frontend deps.
# Prerequisites: uv (https://docs.astral.sh/uv/) and Node 20+ / npm.
set -euo pipefail
cd "$(dirname "$0")"

echo "==> Backend: installing dependencies (uv sync)…"
( cd app/backend && uv sync )

echo "==> Backend: seeding the demo database (8 scenarios)…"
( cd app/backend && uv run python -m claims.seed )

echo "==> Frontend: installing dependencies (npm install)…"
( cd app/frontend && npm install )

echo
echo "Setup complete. Start everything with:  ./dev.sh"
echo "  backend + MCP -> http://localhost:8000   (Swagger: /docs, MCP: /mcp)"
echo "  frontend      -> http://localhost:3000"

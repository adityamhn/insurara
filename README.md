# Claims Processing System

A claims-processing system for **Indian health-insurance reimbursement** claims: submit a
claim with line items → adjudicate each line against frozen policy terms → derive the claim
state from its line items → explain every deduction → dispute and re-derive.

- **Backend:** Python / FastAPI + SQLAlchemy + SQLite, with a pure, deterministic
  adjudication engine at its core.
- **Frontend:** Next.js (App Router, TypeScript) + Tailwind.

See `docs/domain-model.md`, `docs/decisions.md`, and `docs/self-review.md` for the design,
trade-offs, and an honest gap list. `SPEC.md` is the authoritative build spec.

```
app/
  backend/    FastAPI + engine + persistence + tests   (claims/, tests/)
  frontend/   Next.js UI                                (app/, components/, lib/)
docs/         domain-model · decisions · self-review
ai-artifacts/ raw .jsonl agent session logs (required deliverable)
```

---

## Prerequisites
- [uv](https://docs.astral.sh/uv/) (manages Python 3.11+ automatically)
- Node 20+ and npm

## 1. Backend (port 8000)

```bash
cd app/backend
uv sync                              # install deps into .venv
uv run python -m claims.seed         # create claims.db with the 8 demo scenarios
uv run uvicorn claims.api.app:app --port 8000
```

- API docs (Swagger): http://localhost:8000/docs
- Health: http://localhost:8000/health → `{"status":"ok"}`
- Re-run `python -m claims.seed` any time to reset the demo data.

### Tests
```bash
cd app/backend
uv run pytest -q                     # 83 tests
uv run pytest tests/test_worked_example.py    # the §4.4 worked example (₹64,000 → ₹41,400)
```
The engine tests encode domain rules (one per pipeline step + the composite worked
example), not just HTTP status codes.

## 2. Frontend (port 3000)

```bash
cd app/frontend
npm install
npm run dev                          # http://localhost:3000  (expects backend on :8000)
```
The API base URL is configurable via `NEXT_PUBLIC_API_BASE_URL` (default
`http://localhost:8000`). Production build / lint: `npm run build`, `npm run lint`.

---

## Walking the demo (the 8 seeded scenarios)

Open http://localhost:3000 — the claims list shows all eight. Each tells one part of the
story:

| Claim | Scenario | What it shows |
|------:|----------|---------------|
| #1 | **Clean approval** | small claim within limits, no co-pay → `approved`, no deductions |
| #2 | **Room rent + proportionate deduction** (the §4.4 example) | room ₹8,000 → ₹4,500 (cap), surgery ₹40,000 → ₹22,500 (ratio 0.625), pharmacy/diagnostics untouched (IRDAI 2024), 10% co-pay → **₹41,400** payable, `partially_approved` |
| #3 | **Exclusion + dispute** | cosmetic line `denied` (EXCLUDED); a dispute is pre-raised on it — resolve it (overturn) to see re-derivation |
| #4 | **Waiting period** | maternity within its 730-day wait → `denied` |
| #5 | **Sum-insured exhaustion** | policy with ₹2,98,000 already consumed → surgery reduced to the ₹2,000 remaining |
| #6 | **Needs review** ("3 covered, 1 denied, 1 needs review") | implants ₹1,50,000 routes to `under_review`; resolve it via the adjuster panel and watch the claim re-derive |
| #7 | **Family floater** | a dependent draws on the same policy/pool as the primary |
| (any) | **Settle** | settle an approved/partial claim → lines `paid`, then open its policy to see the usage bar move |

The **claim-detail page** is the centerpiece: each line item renders a reason-waterfall
(billed → each deduction with its amount and message → payable), so you can see *why*
₹8,000 became ₹5,000. The same data is available as a printable EOB and via
`GET /api/claims/{id}/explanation`.

### Driving it from the API instead
The interface can be the REST API alone — explore it at `/docs`. Submit a claim with
`POST /api/claims`, then `GET /api/claims/{id}` and `/explanation`; resolve reviews, settle,
and dispute via the documented endpoints.

---

## Reviewer MCP (mounted in the backend)

The same backend process also serves an **MCP server at `http://localhost:8000/mcp`**
(streamable HTTP) — starting `uvicorn` starts it too, no separate process. Point any MCP
client at it to explore the assignment docs (as resources) and drive the live system with
the *same controllers* the REST API uses (so answers match exactly). REST routers and MCP
tools are thin adapters over `claims/application/controllers.py`.

See **`REVIEWER_GUIDE.md`** for connecting a client, the full tool/resource list, and
example questions. Quick check that MCP is live:

```bash
curl -s -X POST localhost:8000/mcp/ \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
```

---

## AI collaboration artifacts

Raw agent session logs (`.jsonl`) covering every phase live in `ai-artifacts/`. They were
copied from the local agent transcript directory:

```bash
# from the repo root — the project's Codex transcript directory:
cp ~/.Codex/projects/-Users-adityapeela-Documents-projects-realfast_assignment/*.jsonl ai-artifacts/
```

Re-run that command to refresh the logs after further work. `ai-artifacts/` is intentionally
**not** gitignored.

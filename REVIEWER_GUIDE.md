# Reviewer Guide

This project ships a **reviewer MCP server mounted inside the backend**. Starting the
backend also starts the MCP endpoint — no separate process. Point any MCP client (Claude
Code, Cursor, Claude Desktop, etc.) at it to explore the assignment docs and drive the live
system with the *same* code paths the REST API and UI use.

- **MCP endpoint (streamable HTTP):** `http://localhost:8000/mcp`
- **REST API / Swagger:** `http://localhost:8000/docs`
- **Web UI:** `http://localhost:3000`

## 1. Start the backend (this also starts MCP)

```bash
cd app/backend
uv sync
uv run python -m claims.seed                 # seed the 8 demo scenarios
uv run uvicorn claims.api.app:app --port 8000
```

Confirm both surfaces respond:
```bash
curl -s localhost:8000/health                # {"status":"ok"}
# MCP initialize handshake (expects an SSE 200 with serverInfo):
curl -s -i -X POST localhost:8000/mcp/ \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}'
```

## 2. Connect an MCP client

Add a **streamable-HTTP** MCP server with URL `http://localhost:8000/mcp`. For example, in
Claude Code:

```bash
claude mcp add --transport http claims-reviewer http://localhost:8000/mcp
```

Or in a client that uses a JSON config:

```json
{
  "mcpServers": {
    "claims-reviewer": { "type": "http", "url": "http://localhost:8000/mcp" }
  }
}
```

## 3. What the server exposes

**Documentation resources** (read-only, quote the checked-in docs verbatim):
`assignment://problem-statement`, `assignment://candidate-instructions`,
`assignment://spec`, `assignment://readme`, `assignment://domain-model`,
`assignment://decisions`, `assignment://self-review`, `assignment://reviewer-guide`,
`assignment://demo-scenarios`. Plus a `search_assignment_docs` tool that returns sourced
snippets (so the agent answers from the docs, not invention).

**Read tools:** `get_demo_status`, `list_demo_scenarios`, `get_claim_summary`,
`get_claim_detail`, `get_claim_explanation`, `get_policy_usage`.

**Mutation tools:** `reset_demo_data`, `submit_claim`, `resolve_review`, `settle_claim`,
`raise_dispute`, `resolve_dispute`, `readjudicate_claim`. These change the demo SQLite data
and return a `warning` saying so — call **`reset_demo_data`** to restore the seeded
scenarios before a clean walkthrough.

Every application tool calls the **same controllers** as the REST API
(`claims/application/controllers.py`), so MCP and REST return identical totals, statuses,
and reasons — there is no second adjudication path.

## 4. Example questions to ask your agent

Demo and verification:

- "Use the claims-reviewer MCP: what does claim #2 show, and why is the payable ₹41,400?"
- "Pull the explanation (EOB) for claim #2 and walk me through each deduction."
- "Reset the demo data, then submit a claim for policy 1 / member 1 on 2024-06-01 with a
  room_rent line of ₹8,000 and a surgery line of ₹40,000. What's the adjudicated payable?"
- "Find claim #6's under-review line and resolve it as denied; what does the claim status
  become?"
- "Show policy 2's usage — how much sum insured remains?"
- "Search the assignment docs for how proportionate deduction works and cite the source."

Design and thought process:

- "Why are coverage rules stored as data rows while the pipeline remains fixed code?"
- "Why is claim status derived from line items instead of written directly?"
- "How do policy snapshots protect old claims from later policy edits?"
- "Why does needs-review run after automatic reductions, not before them?"
- "What production gap would you close first: settlement concurrency, auth/encryption, or
  frontend E2E tests, and why?"
- "From the decisions doc, why was needs-review moved to run last in the pipeline?"

## 5. Notes
- The MCP server is mounted in the FastAPI process (`claims.api.app:create_app`), not a
  separate stdio server. The same `uvicorn` command runs both.
- No domain or adjudication behavior is specific to MCP — it is a thin adapter over the
  shared controllers and the checked-in docs.

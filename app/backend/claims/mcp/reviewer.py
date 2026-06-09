"""Reviewer MCP server.

This adapter is deliberately thin: app-facing tools call the shared controllers,
and assignment-knowledge tools read the checked-in docs. It never reimplements
adjudication, serialization, or scenario setup.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from ..api import schemas
from ..application import controllers
from ..persistence.db import session_scope


REPO_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_URL = "http://localhost:3000"
MCP_URL = "http://localhost:8000/mcp"

DOCS: dict[str, tuple[str, str, str]] = {
    "problem-statement": (
        "assignment://problem-statement",
        "Original problem statement",
        "instructions/problem_statement.md",
    ),
    "candidate-instructions": (
        "assignment://candidate-instructions",
        "Candidate assignment instructions",
        "instructions/candidate_assignment_instructions.md",
    ),
    "spec": ("assignment://spec", "Authoritative build specification", "SPEC.md"),
    "readme": ("assignment://readme", "Setup and demo README", "README.md"),
    "domain-model": (
        "assignment://domain-model",
        "Domain model documentation",
        "docs/domain-model.md",
    ),
    "decisions": ("assignment://decisions", "Decisions and trade-offs", "docs/decisions.md"),
    "self-review": ("assignment://self-review", "Honest self-review", "docs/self-review.md"),
    "reviewer-guide": (
        "assignment://reviewer-guide",
        "Reviewer quick-start guide",
        "REVIEWER_GUIDE.md",
    ),
}

DEMO_SCENARIOS = [
    {
        "scenario": "Clean approval",
        "claim": "#1",
        "what_to_check": "Approved claim with payable equal to billed and no deduction reasons.",
    },
    {
        "scenario": "Room rent + proportionate deduction",
        "claim": "#2",
        "what_to_check": "Flagship waterfall: ₹64,000 billed -> ₹41,400 payable.",
    },
    {
        "scenario": "Exclusion + dispute",
        "claim": "#3",
        "what_to_check": "Cosmetic line denied, pre-raised dispute can be resolved.",
    },
    {
        "scenario": "Waiting period",
        "claim": "#4",
        "what_to_check": "Maternity denied because service is inside the 730-day wait.",
    },
    {
        "scenario": "Sum-insured exhaustion",
        "claim": "#5",
        "what_to_check": "Only ₹2,000 remaining sum insured is payable.",
    },
    {
        "scenario": "Needs review",
        "claim": "#6",
        "what_to_check": "Three covered/reduced, one denied, one under review; claim needs review.",
    },
    {
        "scenario": "Family floater",
        "claim": "#7",
        "what_to_check": "Dependent and primary share the same policy pool.",
    },
    {
        "scenario": "Settlement",
        "claim": "any decided claim",
        "what_to_check": "Settle a decided claim and see policy usage move.",
    },
]


def _read_doc(name: str, *, repo_root: Path = REPO_ROOT) -> str:
    try:
        _, _, relative_path = DOCS[name]
    except KeyError as exc:
        raise ValueError(f"unknown assignment document '{name}'") from exc
    path = repo_root / relative_path
    if not path.exists():
        return f"{relative_path} is not present yet."
    return path.read_text(encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return json.loads(value.model_dump_json())
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    return value


def _dedupe_words(query: str) -> list[str]:
    return sorted({w.lower() for w in re.findall(r"[a-zA-Z0-9_§]+", query) if len(w) > 2})


def search_assignment_docs(
    query: str, *, repo_root: Path = REPO_ROOT, limit: int = 5
) -> dict[str, Any]:
    """Search checked-in assignment docs without inventing unsupported claims."""
    terms = _dedupe_words(query)
    if not terms:
        return {"query": query, "matches": []}

    matches: list[dict[str, Any]] = []
    for name, (uri, title, relative_path) in DOCS.items():
        text = _read_doc(name, repo_root=repo_root)
        lines = text.splitlines()
        for idx, line in enumerate(lines, start=1):
            haystack = line.lower()
            score = sum(1 for term in terms if term in haystack)
            if score == 0:
                continue
            start = max(1, idx - 1)
            end = min(len(lines), idx + 1)
            snippet = "\n".join(lines[start - 1 : end]).strip()
            matches.append(
                {
                    "document": title,
                    "uri": uri,
                    "path": relative_path,
                    "line": idx,
                    "score": score,
                    "snippet": snippet,
                }
            )

    matches.sort(key=lambda m: (-m["score"], m["path"], m["line"]))
    return {"query": query, "matches": matches[:limit]}


@contextmanager
def _controller_session(factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_scope(factory) as session:
        yield session


def get_demo_status(factory: sessionmaker[Session]) -> dict[str, Any]:
    with _controller_session(factory) as session:
        claims = controllers.list_claims(session)
        policies = controllers.list_policies(session)
        worked = controllers.worked_example_claim(session) if claims else None
        return {
            "backend": "healthy",
            "mcp_url": MCP_URL,
            "frontend_url": FRONTEND_URL,
            "claim_count": len(claims),
            "policy_count": len(policies),
            "worked_example": _jsonable(worked) if worked else None,
            "reset_hint": "Call reset_demo_data before a live walkthrough for predictable claim ids.",
        }


def list_demo_scenarios() -> dict[str, Any]:
    return {"scenarios": DEMO_SCENARIOS}


def reset_demo_data(factory: sessionmaker[Session]) -> dict[str, Any]:
    with _controller_session(factory) as session:
        claims = controllers.reset_demo_data(session)
        return {
            "warning": "Demo SQLite data was reset to the seeded assignment scenarios.",
            "claims": _jsonable(claims),
        }


def get_claim_detail(factory: sessionmaker[Session], claim_id: int) -> dict[str, Any]:
    with _controller_session(factory) as session:
        return _jsonable(controllers.get_claim(session, claim_id))


def get_claim_summary(factory: sessionmaker[Session], claim_id: int) -> dict[str, Any]:
    with _controller_session(factory) as session:
        claim = controllers.get_claim(session, claim_id)
        return {
            "id": claim.id,
            "policy_number": claim.policy_number,
            "member_name": claim.member_name,
            "service_date": claim.service_date.isoformat(),
            "stage": claim.stage.value,
            "status": claim.status.value if claim.status else None,
            "totals": _jsonable(claim.totals),
        }


def get_claim_explanation(factory: sessionmaker[Session], claim_id: int) -> dict[str, Any]:
    with _controller_session(factory) as session:
        return _jsonable(controllers.get_explanation(session, claim_id))


def get_policy_usage(factory: sessionmaker[Session], policy_id: int) -> dict[str, Any]:
    with _controller_session(factory) as session:
        policy = controllers.get_policy(session, policy_id)
        return {
            "policy_id": policy.id,
            "policy_number": policy.policy_number,
            "plan_name": policy.plan_name,
            "usage": _jsonable(policy.usage),
            "members": _jsonable(policy.members),
        }


def submit_claim(
    factory: sessionmaker[Session],
    *,
    policy_id: int,
    member_id: int,
    service_date: str,
    line_items: list[dict[str, Any]],
) -> dict[str, Any]:
    body = schemas.ClaimCreate.model_validate(
        {
            "policy_id": policy_id,
            "member_id": member_id,
            "service_date": service_date,
            "line_items": line_items,
        }
    )
    with _controller_session(factory) as session:
        return {
            "warning": "Created a demo claim. Call reset_demo_data to restore seeded scenarios.",
            "claim": _jsonable(controllers.submit_claim(session, body)),
        }


def resolve_review(
    factory: sessionmaker[Session],
    *,
    claim_id: int,
    line_item_id: int,
    decision: str,
    payable_amount: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    body = schemas.ResolveReviewRequest.model_validate(
        {"decision": decision, "payable_amount": payable_amount, "note": note}
    )
    with _controller_session(factory) as session:
        return {
            "warning": "Changed demo claim review state. Call reset_demo_data to restore seeded scenarios.",
            "claim": _jsonable(
                controllers.resolve_line_review(session, claim_id, line_item_id, body)
            ),
        }


def settle_claim(factory: sessionmaker[Session], claim_id: int) -> dict[str, Any]:
    with _controller_session(factory) as session:
        return {
            "warning": "Settled a demo claim and updated usage counters. Call reset_demo_data to restore seeded scenarios.",
            "claim": _jsonable(controllers.settle(session, claim_id)),
        }


def raise_dispute(
    factory: sessionmaker[Session],
    *,
    claim_id: int,
    line_item_id: int | None,
    reason_text: str,
) -> dict[str, Any]:
    body = schemas.DisputeCreate(line_item_id=line_item_id, reason_text=reason_text)
    with _controller_session(factory) as session:
        return {
            "warning": "Raised a demo dispute. Call reset_demo_data to restore seeded scenarios.",
            "dispute": _jsonable(controllers.create_dispute(session, claim_id, body)),
        }


def resolve_dispute(
    factory: sessionmaker[Session],
    *,
    dispute_id: int,
    outcome: str,
    resolution_text: str,
    new_payable_amount: str | None = None,
) -> dict[str, Any]:
    body = schemas.DisputeResolve.model_validate(
        {
            "outcome": outcome,
            "resolution_text": resolution_text,
            "new_payable_amount": new_payable_amount,
        }
    )
    with _controller_session(factory) as session:
        return {
            "warning": "Resolved a demo dispute. Call reset_demo_data to restore seeded scenarios.",
            "dispute": _jsonable(controllers.resolve_dispute_by_id(session, dispute_id, body)),
        }


def readjudicate_claim(factory: sessionmaker[Session], claim_id: int) -> dict[str, Any]:
    with _controller_session(factory) as session:
        return {
            "warning": "Re-adjudicated a demo claim from its frozen snapshot.",
            "claim": _jsonable(controllers.readjudicate(session, claim_id)),
        }


def create_reviewer_mcp(
    session_factory: sessionmaker[Session],
    *,
    repo_root: Path = REPO_ROOT,
) -> FastMCP:
    mcp = FastMCP(
        "Claims Processing Reviewer",
        instructions=(
            "Use these tools to review the Claims Processing assignment. "
            "Application tools call the same controllers as the REST API; "
            "documentation tools only quote checked-in assignment documents."
        ),
        streamable_http_path="/",
    )

    @mcp.resource("assignment://problem-statement", mime_type="text/markdown")
    def problem_statement() -> str:
        return _read_doc("problem-statement", repo_root=repo_root)

    @mcp.resource("assignment://candidate-instructions", mime_type="text/markdown")
    def candidate_instructions() -> str:
        return _read_doc("candidate-instructions", repo_root=repo_root)

    @mcp.resource("assignment://spec", mime_type="text/markdown")
    def spec() -> str:
        return _read_doc("spec", repo_root=repo_root)

    @mcp.resource("assignment://readme", mime_type="text/markdown")
    def readme() -> str:
        return _read_doc("readme", repo_root=repo_root)

    @mcp.resource("assignment://domain-model", mime_type="text/markdown")
    def domain_model() -> str:
        return _read_doc("domain-model", repo_root=repo_root)

    @mcp.resource("assignment://decisions", mime_type="text/markdown")
    def decisions() -> str:
        return _read_doc("decisions", repo_root=repo_root)

    @mcp.resource("assignment://self-review", mime_type="text/markdown")
    def self_review() -> str:
        return _read_doc("self-review", repo_root=repo_root)

    @mcp.resource("assignment://reviewer-guide", mime_type="text/markdown")
    def reviewer_guide() -> str:
        return _read_doc("reviewer-guide", repo_root=repo_root)

    @mcp.resource("assignment://demo-scenarios", mime_type="application/json")
    def demo_scenarios_resource() -> str:
        return json.dumps(list_demo_scenarios(), indent=2)

    @mcp.tool(
        name="search_assignment_docs",
        description="Search only checked-in assignment docs; returns sourced snippets.",
    )
    def search_assignment_docs_tool(query: str, limit: int = 5) -> dict[str, Any]:
        return search_assignment_docs(query, repo_root=repo_root, limit=limit)

    @mcp.tool(
        name="get_demo_status",
        description="Check seeded demo status and the flagship worked-example claim.",
    )
    def get_demo_status_tool() -> dict[str, Any]:
        return get_demo_status(session_factory)

    @mcp.tool(
        name="list_demo_scenarios",
        description="List the assignment demo scenarios in plain English.",
    )
    def list_demo_scenarios_tool() -> dict[str, Any]:
        return list_demo_scenarios()

    @mcp.tool(
        name="reset_demo_data",
        description="Reset the demo SQLite database to seeded assignment scenarios.",
    )
    def reset_demo_data_tool() -> dict[str, Any]:
        return reset_demo_data(session_factory)

    @mcp.tool(name="get_claim_summary", description="Get a compact claim summary by id.")
    def get_claim_summary_tool(claim_id: int) -> dict[str, Any]:
        return get_claim_summary(session_factory, claim_id)

    @mcp.tool(
        name="get_claim_detail",
        description="Get full claim detail, including line items, reasons, logs, and disputes.",
    )
    def get_claim_detail_tool(claim_id: int) -> dict[str, Any]:
        return get_claim_detail(session_factory, claim_id)

    @mcp.tool(
        name="get_claim_explanation",
        description="Get the member-facing Explanation of Benefits waterfall for a claim.",
    )
    def get_claim_explanation_tool(claim_id: int) -> dict[str, Any]:
        return get_claim_explanation(session_factory, claim_id)

    @mcp.tool(
        name="get_policy_usage",
        description="Get live policy usage counters and insured members.",
    )
    def get_policy_usage_tool(policy_id: int) -> dict[str, Any]:
        return get_policy_usage(session_factory, policy_id)

    @mcp.tool(
        name="submit_claim",
        description="Create and adjudicate a demo claim through the shared controller.",
    )
    def submit_claim_tool(
        policy_id: int,
        member_id: int,
        service_date: str,
        line_items: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return submit_claim(
            session_factory,
            policy_id=policy_id,
            member_id=member_id,
            service_date=service_date,
            line_items=line_items,
        )

    @mcp.tool(
        name="resolve_review",
        description="Resolve an under-review demo line item through the shared controller.",
    )
    def resolve_review_tool(
        claim_id: int,
        line_item_id: int,
        decision: str,
        payable_amount: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        return resolve_review(
            session_factory,
            claim_id=claim_id,
            line_item_id=line_item_id,
            decision=decision,
            payable_amount=payable_amount,
            note=note,
        )

    @mcp.tool(
        name="settle_claim",
        description="Settle a demo claim and update live usage counters.",
    )
    def settle_claim_tool(claim_id: int) -> dict[str, Any]:
        return settle_claim(session_factory, claim_id)

    @mcp.tool(
        name="raise_dispute",
        description="Raise a demo dispute on a claim or line item.",
    )
    def raise_dispute_tool(
        claim_id: int,
        reason_text: str,
        line_item_id: int | None = None,
    ) -> dict[str, Any]:
        return raise_dispute(
            session_factory,
            claim_id=claim_id,
            line_item_id=line_item_id,
            reason_text=reason_text,
        )

    @mcp.tool(
        name="resolve_dispute",
        description="Resolve a demo dispute as upheld or overturned.",
    )
    def resolve_dispute_tool(
        dispute_id: int,
        outcome: str,
        resolution_text: str,
        new_payable_amount: str | None = None,
    ) -> dict[str, Any]:
        return resolve_dispute(
            session_factory,
            dispute_id=dispute_id,
            outcome=outcome,
            resolution_text=resolution_text,
            new_payable_amount=new_payable_amount,
        )

    @mcp.tool(
        name="readjudicate_claim",
        description="Re-run adjudication from the claim's frozen policy snapshot.",
    )
    def readjudicate_claim_tool(claim_id: int) -> dict[str, Any]:
        return readjudicate_claim(session_factory, claim_id)

    return mcp

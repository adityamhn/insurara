"""Reviewer MCP tests.

The MCP tools are thin wrappers over the functions in `claims/mcp/reviewer.py`, which call
the same controllers as REST. We test those functions directly (no transport) for parity
and behavior; the live streamable-HTTP transport is exercised by the README/REVIEWER_GUIDE
smoke check. End-to-end transport correctness was also verified against a running server."""

from __future__ import annotations

import pytest

from claims.application import controllers
from claims.mcp import reviewer


def _shape(claim: dict) -> dict:
    return {
        "status": claim["status"],
        "stage": claim["stage"],
        "totals": claim["totals"],
        "lines": [
            {
                "code": li["coverage_type_code"],
                "payable": li["payable_amount"],
                "status": li["status"],
                "reasons": [r["code"] for r in li["reasons"]],
            }
            for li in claim["line_items"]
        ],
    }


# --- Parity: MCP returns the same totals/status/reasons as the controller ---- #
def test_mcp_claim_detail_matches_controller(seeded_factory):
    mcp_claim = reviewer.get_claim_detail(seeded_factory, 2)
    with seeded_factory() as s:
        ctrl_claim = controllers.get_claim(s, 2).model_dump(mode="json")
    assert _shape(mcp_claim) == _shape(ctrl_claim)
    assert mcp_claim["totals"]["total_billed"] == "64000.00"
    assert mcp_claim["totals"]["total_payable"] == "41400.00"


def test_mcp_explanation_and_policy_usage(seeded_factory):
    eob = reviewer.get_claim_explanation(seeded_factory, 2)
    assert eob["totals"]["total_payable"] == "41400.00"
    usage = reviewer.get_policy_usage(seeded_factory, 2)
    assert usage["usage"]["sum_insured_remaining"] == "2000.00"


def test_mcp_demo_status(seeded_factory):
    status = reviewer.get_demo_status(seeded_factory)
    assert status["backend"] == "healthy"
    assert status["claim_count"] == 7
    assert status["worked_example"]["totals"]["total_payable"] == "41400.00"


# --- Documentation resources / search --------------------------------------- #
def test_mcp_read_doc_and_unknown():
    assert "Sum Insured" in reviewer._read_doc("spec")
    assert "Reviewer Guide" in reviewer._read_doc("reviewer-guide")
    with pytest.raises(ValueError):
        reviewer._read_doc("does-not-exist")


def test_mcp_search_returns_sourced_snippets():
    result = reviewer.search_assignment_docs("proportionate deduction")
    assert result["matches"], "expected matches for a real domain term"
    top = result["matches"][0]
    assert {"document", "uri", "path", "line", "snippet"} <= top.keys()
    # A nonsense query returns nothing rather than inventing an answer.
    assert reviewer.search_assignment_docs("zzqq")["matches"] == []


# --- Mutation + reset flow (review → settle, then restore) ------------------- #
def test_mcp_reset_review_settle_flow(seeded_factory):
    reviewer.reset_demo_data(seeded_factory)

    # Claim #6 is the needs-review scenario; find its under_review line.
    claim = reviewer.get_claim_detail(seeded_factory, 6)
    assert claim["status"] == "needs_review"
    review_line = next(li for li in claim["line_items"] if li["status"] == "under_review")

    resolved = reviewer.resolve_review(
        seeded_factory, claim_id=6, line_item_id=review_line["id"], decision="deny"
    )
    assert "warning" in resolved
    assert resolved["claim"]["status"] == "partially_approved"

    settled = reviewer.settle_claim(seeded_factory, 6)
    assert settled["claim"]["stage"] == "settled"
    assert all(li["status"] in ("paid", "denied") for li in settled["claim"]["line_items"])

    # Reset restores the seeded story for the next reviewer.
    after = reviewer.reset_demo_data(seeded_factory)
    assert len(after["claims"]) == 7

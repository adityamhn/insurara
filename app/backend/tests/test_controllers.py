"""Controller use-case tests + REST↔controller parity.

Controllers (`claims/application/controllers.py`) are the shared seam both the REST routers
and the MCP server call. These tests exercise them directly and prove the REST adapter
returns exactly what the controller produces."""

from __future__ import annotations

from decimal import Decimal

from fastapi.testclient import TestClient

from claims.api.app import create_app
from claims.application import controllers


def _claim_shape(d: dict) -> dict:
    """The parts that matter for parity: totals, status, and per-line reasons."""
    return {
        "status": d["status"],
        "stage": d["stage"],
        "totals": d["totals"],
        "lines": [
            {
                "code": li["coverage_type_code"],
                "payable": li["payable_amount"],
                "status": li["status"],
                "reasons": [r["code"] for r in li["reasons"]],
            }
            for li in d["line_items"]
        ],
    }


# --- Controller use cases ---------------------------------------------------- #
def test_controller_reference_data(seeded):
    session, _ = seeded
    assert len(controllers.list_plans(session)) == 2
    assert len(controllers.list_members(session)) == 4
    assert len(controllers.list_policies(session)) >= 3


def test_controller_worked_example(seeded):
    session, _ = seeded
    claim = controllers.worked_example_claim(session)
    assert claim.totals.total_billed == Decimal("64000.00")
    assert claim.totals.total_payable == Decimal("41400.00")
    assert claim.status.value == "partially_approved"


def test_controller_get_policy_usage(seeded):
    session, _ = seeded
    policies = controllers.list_policies(session)
    exhaust = next(p for p in policies if p.policy_number == "AS3L-EXHAUST-0002")
    full = controllers.get_policy(session, exhaust.id)
    assert full.usage.sum_insured_remaining == Decimal("2000.00")


def test_controller_dispute_list_reflects_seed(seeded):
    session, claims = seeded
    # The exclusion claim has a pre-raised dispute (seed scenario 8).
    disputes = controllers.list_disputes(session, claims["exclusion"].id)
    assert len(disputes) == 1
    assert disputes[0].state.value == "raised"


def test_controller_reset_demo_data(session):
    # Empty DB → reset rebuilds the seeded scenarios.
    summaries = controllers.reset_demo_data(session)
    assert len(summaries) == 7
    assert any(s.totals.total_payable == Decimal("41400.00") for s in summaries)


# --- REST ↔ controller parity ------------------------------------------------ #
def test_rest_matches_controller_for_claim_2(seeded_factory):
    client = TestClient(create_app(seeded_factory))
    rest = client.get("/api/claims/2").json()
    with seeded_factory() as s:
        ctrl = controllers.get_claim(s, 2).model_dump(mode="json")
    assert _claim_shape(rest) == _claim_shape(ctrl)
    assert rest["totals"]["total_payable"] == "41400.00"


def test_rest_matches_controller_for_policy_usage(seeded_factory):
    client = TestClient(create_app(seeded_factory))
    rest = client.get("/api/policies/2").json()
    with seeded_factory() as s:
        ctrl = controllers.get_policy(s, 2).model_dump(mode="json")
    assert rest["usage"] == ctrl["usage"]

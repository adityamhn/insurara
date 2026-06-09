"""Settlement + usage counters and review resolution (SPEC §3.3, §5.3).

Covers: counters move on settlement (not adjudication), the can't-settle-with-review
guard, the review → re-derive → settle loop, and limit exhaustion across sequential
claims (the stateful-across-time requirement)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from claims.domain.models import LineItemInput
from claims.persistence import models as orm
from claims.service.claims import create_claim, settle_claim


def _policy_and_member(client, policy_number: str):
    policies = client.get("/api/policies").json()
    policy = next(p for p in policies if p["policy_number"] == policy_number)
    return policy["id"], policy["members"][0]["member_id"]


def _surgery_claim(client, pid, mid, *amounts, service_date="2024-06-01"):
    return client.post(
        "/api/claims",
        json={
            "policy_id": pid,
            "member_id": mid,
            "service_date": service_date,
            "line_items": [{"coverage_type_code": "surgery", "billed_amount": a} for a in amounts],
        },
    ).json()


# --- Settlement counters ----------------------------------------------------- #
def test_settle_pays_lines_and_increments_sum_insured(client):
    pid, mid = _policy_and_member(client, "AS3L-CLEAN-0003")  # SI 3,00,000, no copay
    claim = _surgery_claim(client, pid, mid, "90000")
    assert claim["status"] == "approved"

    settled = client.post(f"/api/claims/{claim['id']}/settle").json()
    assert settled["stage"] == "settled"
    assert all(li["status"] == "paid" for li in settled["line_items"])

    usage = client.get(f"/api/policies/{pid}").json()["usage"]
    assert usage["sum_insured_consumed"] == "90000.00"
    assert usage["sum_insured_remaining"] == "210000.00"


def test_settle_is_blocked_while_a_line_is_under_review(client):
    needs = client.get("/api/claims", params={"status": "needs_review"}).json()
    resp = client.post(f"/api/claims/{needs[0]['id']}/settle")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_double_settle_conflicts(client):
    pid, mid = _policy_and_member(client, "AS3L-CLEAN-0003")
    claim = _surgery_claim(client, pid, mid, "90000")
    client.post(f"/api/claims/{claim['id']}/settle")
    resp = client.post(f"/api/claims/{claim['id']}/settle")
    assert resp.status_code == 409


# --- Review resolution loop -------------------------------------------------- #
def test_resolve_review_then_settle(client):
    needs = client.get("/api/claims", params={"status": "needs_review"}).json()
    claim = client.get(f"/api/claims/{needs[0]['id']}").json()
    review_line = next(li for li in claim["line_items"] if li["status"] == "under_review")

    resolved = client.post(
        f"/api/claims/{claim['id']}/line-items/{review_line['id']}/resolve-review",
        json={"decision": "deny", "note": "not medically necessary"},
    )
    assert resolved.status_code == 200
    # was needs_review (3 partial, 1 denied, 1 review) -> now 3 partial, 2 denied.
    assert resolved.json()["status"] == "partially_approved"
    assert resolved.json()["stage"] == "decided"

    settled = client.post(f"/api/claims/{claim['id']}/settle")
    assert settled.status_code == 200
    assert all(li["status"] in ("paid", "denied") for li in settled.json()["line_items"])


def test_resolve_review_partial_sets_payable(client):
    needs = client.get("/api/claims", params={"status": "needs_review"}).json()
    claim = client.get(f"/api/claims/{needs[0]['id']}").json()
    review_line = next(li for li in claim["line_items"] if li["status"] == "under_review")

    resolved = client.post(
        f"/api/claims/{claim['id']}/line-items/{review_line['id']}/resolve-review",
        json={"decision": "partially_approve", "payable_amount": "50000"},
    ).json()
    line = next(li for li in resolved["line_items"] if li["id"] == review_line["id"])
    assert line["status"] == "partially_approved"
    assert line["payable_amount"] == "50000.00"


def test_resolve_partial_without_amount_is_rejected(client):
    needs = client.get("/api/claims", params={"status": "needs_review"}).json()
    claim = client.get(f"/api/claims/{needs[0]['id']}").json()
    review_line = next(li for li in claim["line_items"] if li["status"] == "under_review")
    resp = client.post(
        f"/api/claims/{claim['id']}/line-items/{review_line['id']}/resolve-review",
        json={"decision": "partially_approve"},
    )
    assert resp.status_code == 400


# --- Stateful across time: exhaustion across sequential claims --------------- #
def test_sum_insured_exhausts_across_sequential_settled_claims(client):
    pid, mid = _policy_and_member(client, "AS3L-CLEAN-0003")  # SI 3,00,000

    first = _surgery_claim(client, pid, mid, "90000", "90000")  # 1,80,000
    client.post(f"/api/claims/{first['id']}/settle")
    assert (
        client.get(f"/api/policies/{pid}").json()["usage"]["sum_insured_remaining"] == "120000.00"
    )

    # Second claim, created AFTER settlement, sees only ₹1,20,000 of headroom.
    second = _surgery_claim(client, pid, mid, "90000", "90000", service_date="2024-07-01")
    payables = sorted(li["payable_amount"] for li in second["line_items"])
    assert payables == ["30000.00", "90000.00"]  # second line capped to remaining SI
    assert second["status"] == "partially_approved"
    assert second["totals"]["total_payable"] == "120000.00"


def test_per_year_sub_limit_accumulates_across_claims(client):
    pid, mid = _policy_and_member(client, "AS3L-CLEAN-0003")

    def dental(amount, service_date):
        return client.post(
            "/api/claims",
            json={
                "policy_id": pid,
                "member_id": mid,
                "service_date": service_date,
                "line_items": [{"coverage_type_code": "dental", "billed_amount": amount}],
            },
        ).json()

    first = dental("6000", "2024-03-01")
    assert first["status"] == "approved"
    client.post(f"/api/claims/{first['id']}/settle")
    consumed = client.get(f"/api/policies/{pid}").json()["usage"]["sub_limit_consumed"]
    assert consumed["dental"] == "6000.00"

    # Annual dental cap is ₹10,000; only ₹4,000 remains for the next claim.
    second = dental("6000", "2024-04-01")
    assert second["line_items"][0]["payable_amount"] == "4000.00"
    assert second["status"] == "partially_approved"


# --- Deductible counter (service-level; no seed plan carries a deductible) ---- #
def test_settlement_increments_deductible_consumed(session):
    plan = orm.CoveragePlan(
        name="Deductible Plan",
        sum_insured=Decimal("100000"),
        deductible=Decimal("5000"),
        coverage_types=[orm.CoverageType(code="surgery", name="Surgery")],
    )
    session.add(plan)
    session.flush()
    member = orm.Member(name="Test Member", dob=date(1990, 1, 1))
    session.add(member)
    session.flush()
    policy = orm.Policy(
        policy_number="DED-0001",
        plan_id=plan.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        members=[orm.PolicyMember(member_id=member.id, role="primary")],
    )
    session.add(policy)
    session.flush()

    claim = create_claim(
        session,
        policy_id=policy.id,
        member_id=member.id,
        service_date=date(2024, 6, 1),
        line_items=[
            LineItemInput(ref="s", coverage_type_code="surgery", billed_amount=Decimal("20000"))
        ],
    )
    settle_claim(session, claim)
    session.refresh(policy)
    assert policy.deductible_consumed == Decimal("5000.00")
    assert policy.sum_insured_consumed == Decimal("15000.00")  # 20,000 - 5,000 deductible

"""API integration tests (SPEC §5): submit→adjudicate happy path + key guards.
Exercises the full stack — HTTP → service → engine → DB — not just status codes."""

from __future__ import annotations


def _policy_and_member(client, policy_number: str):
    policies = client.get("/api/policies").json()
    policy = next(p for p in policies if p["policy_number"] == policy_number)
    return policy, policy["members"][0]["member_id"]


def _worked_example_body(client):
    policy, member_id = _policy_and_member(client, "HS5L-FAMILY-0001")
    return {
        "policy_id": policy["id"],
        "member_id": member_id,
        "service_date": "2024-06-01",
        "line_items": [
            {"coverage_type_code": "room_rent", "billed_amount": "8000"},
            {"coverage_type_code": "surgery", "billed_amount": "40000"},
            {"coverage_type_code": "pharmacy", "billed_amount": "6000"},
            {"coverage_type_code": "diagnostics", "billed_amount": "10000"},
        ],
    }


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_reference_endpoints_return_seeded_data(client):
    assert len(client.get("/api/plans").json()) == 2
    assert len(client.get("/api/members").json()) == 4
    policies = client.get("/api/policies").json()
    # Usage is exposed so the UI can show limit exhaustion.
    exhaust = next(p for p in policies if p["policy_number"] == "AS3L-EXHAUST-0002")
    assert exhaust["usage"]["sum_insured_remaining"] == "2000.00"


def test_submit_claim_reproduces_worked_example(client):
    resp = client.post("/api/claims", json=_worked_example_body(client))
    assert resp.status_code == 201
    claim = resp.json()
    assert claim["status"] == "partially_approved"
    assert claim["stage"] == "decided"
    assert claim["totals"]["total_payable"] == "41400.00"
    assert claim["totals"]["total_billed"] == "64000.00"


def test_submitted_claim_is_retrievable_with_reasons(client):
    claim_id = client.post("/api/claims", json=_worked_example_body(client)).json()["id"]
    detail = client.get(f"/api/claims/{claim_id}").json()
    room = next(li for li in detail["line_items"] if li["coverage_type_code"] == "room_rent")
    codes = [r["code"] for r in room["reasons"]]
    assert "SUB_LIMIT" in codes
    assert detail["decision_logs"]  # activity stream present


def test_explanation_is_a_per_line_waterfall(client):
    claim_id = client.post("/api/claims", json=_worked_example_body(client)).json()["id"]
    eob = client.get(f"/api/claims/{claim_id}/explanation").json()
    surgery = next(li for li in eob["lines"] if li["coverage_type_code"] == "surgery")
    assert surgery["billed_amount"] == "40000.00"
    assert any(s["code"] == "PROPORTIONATE_DEDUCTION" for s in surgery["steps"])
    assert surgery["payable_amount"] == "22500.00"  # 25000 after copay
    assert eob["totals"]["total_payable"] == "41400.00"


def test_list_claims_filter_by_status(client):
    needs = client.get("/api/claims", params={"status": "needs_review"}).json()
    assert len(needs) >= 1
    assert all(c["status"] == "needs_review" for c in needs)


def test_submit_with_member_not_on_policy_returns_400(client):
    body = _worked_example_body(client)
    # Meera (policy B) is not on the family policy.
    meera = next(m for m in client.get("/api/members").json() if m["name"] == "Meera Nair")
    body["member_id"] = meera["id"]
    resp = client.post("/api/claims", json=body)
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_claim"


def test_unknown_claim_returns_404(client):
    resp = client.get("/api/claims/99999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_submit_with_no_line_items_is_rejected(client):
    policy, member_id = _policy_and_member(client, "HS5L-FAMILY-0001")
    resp = client.post(
        "/api/claims",
        json={
            "policy_id": policy["id"],
            "member_id": member_id,
            "service_date": "2024-06-01",
            "line_items": [],
        },
    )
    assert resp.status_code == 422  # schema guard: min_length=1

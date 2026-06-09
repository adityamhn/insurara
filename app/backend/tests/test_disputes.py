"""Disputes (SPEC §5.4): raise → re-open, resolve upheld (restore) / overturned
(re-decide + re-derive), and readjudicate as a reset. Full HTTP stack."""

from __future__ import annotations


def _claims(client, **params):
    return client.get("/api/claims", params=params).json()


def _first(client, status):
    return _claims(client, status=status)[0]


# --- Raise ------------------------------------------------------------------- #
def test_raise_dispute_marks_line_disputed_and_reopens_claim(client):
    claim = client.get(f"/api/claims/{_first(client, 'denied')['id']}").json()
    line = claim["line_items"][0]

    resp = client.post(
        f"/api/claims/{claim['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "emergency treatment"},
    )
    assert resp.status_code == 201
    assert resp.json()["state"] == "raised"
    assert resp.json()["prior_status"] == "denied"

    detail = client.get(f"/api/claims/{claim['id']}").json()
    assert detail["line_items"][0]["status"] == "disputed"
    assert detail["stage"] == "under_adjudication"


def test_cannot_dispute_a_settled_claim(client):
    approved = _first(client, "approved")
    client.post(f"/api/claims/{approved['id']}/settle")
    line = client.get(f"/api/claims/{approved['id']}").json()["line_items"][0]
    resp = client.post(
        f"/api/claims/{approved['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "x"},
    )
    assert resp.status_code == 409


# --- Resolve: overturned ----------------------------------------------------- #
def test_overturn_denied_line_approves_and_rederives(client):
    claim = client.get(f"/api/claims/{_first(client, 'denied')['id']}").json()
    line = claim["line_items"][0]
    billed = line["billed_amount"]
    dispute = client.post(
        f"/api/claims/{claim['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "appeal"},
    ).json()

    resolved = client.post(
        f"/api/disputes/{dispute['id']}/resolve",
        json={"outcome": "overturned", "resolution_text": "approved on appeal"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["state"] == "overturned"

    detail = client.get(f"/api/claims/{claim['id']}").json()
    dl = detail["line_items"][0]
    assert dl["status"] == "approved"
    assert dl["payable_amount"] == billed  # overturn to full when no amount given
    assert detail["status"] == "approved"
    assert any(r["code"] == "DISPUTE_OVERTURNED" for r in dl["reasons"])


def test_overturn_with_corrected_amount_partially_approves(client):
    claim = client.get(f"/api/claims/{_first(client, 'denied')['id']}").json()
    line = claim["line_items"][0]
    dispute = client.post(
        f"/api/claims/{claim['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "appeal"},
    ).json()
    resolved = client.post(
        f"/api/disputes/{dispute['id']}/resolve",
        json={
            "outcome": "overturned",
            "resolution_text": "partial allowance",
            "new_payable_amount": "20000",
        },
    ).json()
    assert resolved["state"] == "overturned"
    dl = client.get(f"/api/claims/{claim['id']}").json()["line_items"][0]
    assert dl["status"] == "partially_approved"
    assert dl["payable_amount"] == "20000.00"


def test_overturn_amount_above_billed_is_rejected(client):
    claim = client.get(f"/api/claims/{_first(client, 'denied')['id']}").json()
    line = claim["line_items"][0]
    dispute = client.post(
        f"/api/claims/{claim['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "appeal"},
    ).json()
    resp = client.post(
        f"/api/disputes/{dispute['id']}/resolve",
        json={"outcome": "overturned", "resolution_text": "x", "new_payable_amount": "999999"},
    )
    assert resp.status_code == 400


# --- Resolve: upheld --------------------------------------------------------- #
def test_upheld_restores_prior_decision(client):
    claim = client.get(f"/api/claims/{_first(client, 'denied')['id']}").json()
    line = claim["line_items"][0]
    dispute = client.post(
        f"/api/claims/{claim['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "appeal"},
    ).json()
    resolved = client.post(
        f"/api/disputes/{dispute['id']}/resolve",
        json={"outcome": "upheld", "resolution_text": "waiting period applies"},
    ).json()
    assert resolved["state"] == "upheld"

    detail = client.get(f"/api/claims/{claim['id']}").json()
    assert detail["line_items"][0]["status"] == "denied"  # restored
    assert detail["status"] == "denied"


def test_cannot_resolve_a_dispute_twice(client):
    claim = client.get(f"/api/claims/{_first(client, 'denied')['id']}").json()
    line = claim["line_items"][0]
    dispute = client.post(
        f"/api/claims/{claim['id']}/disputes",
        json={"line_item_id": line["id"], "reason_text": "appeal"},
    ).json()
    body = {"outcome": "upheld", "resolution_text": "stands"}
    assert client.post(f"/api/disputes/{dispute['id']}/resolve", json=body).status_code == 200
    assert client.post(f"/api/disputes/{dispute['id']}/resolve", json=body).status_code == 409


def test_resolve_unknown_dispute_404(client):
    resp = client.post(
        "/api/disputes/99999/resolve",
        json={"outcome": "upheld", "resolution_text": "x"},
    )
    assert resp.status_code == 404


# --- Seed scenario + readjudicate -------------------------------------------- #
def test_seed_includes_an_open_dispute(client):
    with_disputes = [
        c for c in _claims(client) if client.get(f"/api/claims/{c['id']}/disputes").json()
    ]
    assert with_disputes
    dispute = client.get(f"/api/claims/{with_disputes[0]['id']}/disputes").json()[0]
    assert dispute["state"] == "raised"
    assert dispute["prior_status"] == "denied"


def test_readjudicate_resets_manual_overrides(client):
    needs = _first(client, "needs_review")
    claim = client.get(f"/api/claims/{needs['id']}").json()
    review_line = next(li for li in claim["line_items"] if li["status"] == "under_review")

    # Manually deny the review line, then reset via readjudicate.
    client.post(
        f"/api/claims/{claim['id']}/line-items/{review_line['id']}/resolve-review",
        json={"decision": "deny"},
    )
    reset = client.post(f"/api/claims/{claim['id']}/readjudicate").json()
    assert reset["status"] == "needs_review"
    implants = next(li for li in reset["line_items"] if li["coverage_type_code"] == "implants")
    assert implants["status"] == "under_review"

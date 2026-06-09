"""Persistence + service round-trips: the engine's decision survives a DB round-trip,
money stays exact, and snapshots are immune to later policy edits (Decision 7)."""

from decimal import Decimal

from claims.domain.enums import ClaimStatus, ReasonCode
from claims.domain.models import LineItemInput
from claims.domain.money import rupee
from claims.engine.pipeline import adjudicate_claim
from claims.service.snapshot import load_snapshot_dtos


def test_worked_example_persists_with_ordered_reasons(seeded):
    session, claims = seeded
    claim = claims["proportionate"]
    session.refresh(claim)

    assert claim.status is ClaimStatus.PARTIALLY_APPROVED
    total = sum((li.payable_amount for li in claim.line_items), Decimal("0"))
    assert total == rupee("41400")

    room = next(li for li in claim.line_items if li.coverage_type_code == "room_rent")
    # Reasons persisted in pipeline order (ordinal 0..n).
    assert [r.ordinal for r in room.reasons] == list(range(len(room.reasons)))
    assert any(r.code is ReasonCode.SUB_LIMIT for r in room.reasons)


def test_money_column_roundtrips_as_decimal(seeded):
    _, claims = seeded
    li = claims["proportionate"].line_items[0]
    assert isinstance(li.billed_amount, Decimal)
    assert li.billed_amount == li.billed_amount.quantize(Decimal("0.01"))


def test_decision_log_records_submission_and_adjudication(seeded):
    session, claims = seeded
    claim = claims["proportionate"]
    session.refresh(claim)
    messages = [log.message for log in claim.decision_logs]
    assert any("submitted" in m.lower() for m in messages)
    assert any("adjudicated" in m.lower() for m in messages)


def test_snapshot_isolated_from_later_policy_edits(seeded):
    session, claims = seeded
    claim = claims["proportionate"]

    snap, usage = load_snapshot_dtos(claim.snapshot)
    assert snap.copay_percent == Decimal("10")

    # Edit the LIVE plan after the claim was created.
    claim.policy.plan.copay_percent = Decimal("0")
    session.commit()

    # The snapshot is frozen, and re-adjudicating from it still yields ₹41,400.
    snap2, usage2 = load_snapshot_dtos(claim.snapshot)
    assert snap2.copay_percent == Decimal("10")
    inputs = [
        LineItemInput(
            ref=li.ref,
            coverage_type_code=li.coverage_type_code,
            billed_amount=li.billed_amount,
            service_days=li.service_days,
        )
        for li in claim.line_items
    ]
    result = adjudicate_claim(snap2, inputs, usage2, claim.service_date)
    assert result.totals.total_payable == rupee("41400")

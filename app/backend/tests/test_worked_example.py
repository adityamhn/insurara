"""The SPEC §4.4 worked example — MANDATORY. ₹64,000 billed → ₹41,400 payable.

Policy: SI ₹5,00,000; room-rent sub-limit 1% of SI = ₹5,000/day; co-pay 10%; no
deductible. One-day hospitalization with four line items.
"""

from datetime import date
from decimal import Decimal

from claims.domain.enums import ClaimStage, ClaimStatus, LineItemStatus, ReasonCode
from claims.domain.money import rupee
from claims.engine.pipeline import adjudicate_claim

from .helpers import line, snapshot, usage

SERVICE_DATE = date(2024, 6, 1)


def _result():
    snap = snapshot(
        sum_insured="500000",
        copay_percent="10",
        codes=["room_rent", "surgery", "pharmacy", "diagnostics"],
    )
    lines = [
        line("room_rent", "8000", ref="room"),
        line("surgery", "40000", ref="surgery"),
        line("pharmacy", "6000", ref="pharmacy"),
        line("diagnostics", "10000", ref="mri"),
    ]
    return adjudicate_claim(snap, lines, usage(), SERVICE_DATE)


def test_claim_total_payable_is_41400():
    result = _result()
    assert result.totals.total_billed == rupee("64000")
    assert result.totals.total_payable == rupee("41400")
    assert result.totals.total_member_borne == rupee("22600")


def test_claim_is_partially_approved_and_decided():
    result = _result()
    assert result.status is ClaimStatus.PARTIALLY_APPROVED
    assert result.stage is ClaimStage.DECIDED
    assert all(li.status is LineItemStatus.PARTIALLY_APPROVED for li in result.line_items)


def test_intermediate_line_values_match_spec():
    """Room capped to ₹5,000 (ratio 0.625); surgery scaled to ₹25,000; pharmacy &
    diagnostics untouched by proportionate deduction (IRDAI 2024). Then 10% copay."""
    by_ref = {li.ref: li for li in _result().line_items}

    # Room: SUB_LIMIT brings 8000 -> 5000 (excess 3000), then 10% copay -> 4500.
    room = by_ref["room"]
    sub_limit = next(r for r in room.reasons if r.code is ReasonCode.SUB_LIMIT)
    assert sub_limit.amount_delta == rupee("-3000")
    assert room.billed_amount + sub_limit.amount_delta == rupee("5000")
    assert room.payable_amount == rupee("4500")

    # Surgery: PROPORTIONATE 40000 -> 25000 (delta -15000), then copay -> 22500.
    surgery = by_ref["surgery"]
    prop = next(r for r in surgery.reasons if r.code is ReasonCode.PROPORTIONATE_DEDUCTION)
    assert prop.amount_delta == rupee("-15000")
    assert surgery.billed_amount + prop.amount_delta == rupee("25000")
    assert surgery.payable_amount == rupee("22500")

    # Pharmacy & diagnostics: NOT proportionately deducted; only the 10% copay applies.
    pharmacy = by_ref["pharmacy"]
    assert not any(r.code is ReasonCode.PROPORTIONATE_DEDUCTION for r in pharmacy.reasons)
    assert pharmacy.payable_amount == rupee("5400")

    diagnostics = by_ref["mri"]
    assert not any(r.code is ReasonCode.PROPORTIONATE_DEDUCTION for r in diagnostics.reasons)
    assert diagnostics.payable_amount == rupee("9000")


def test_every_reason_amount_is_decimal_two_places():
    for li in _result().line_items:
        for r in li.reasons:
            assert isinstance(r.amount_delta, Decimal)
            assert -r.amount_delta == (-r.amount_delta).quantize(Decimal("0.01"))

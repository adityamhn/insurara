"""Proportionate deduction — the most domain-accurate rule (SPEC §4.3, IRDAI 2024).

When room rent breaches its sub-limit, associated charges scale by the same ratio;
pharmacy, implants, and diagnostics are explicitly excluded from the scaling.
"""

from datetime import date

from claims.domain.enums import LineItemStatus, ReasonCode
from claims.domain.money import rupee
from claims.engine.pipeline import adjudicate_claim

from .helpers import line, snapshot, usage

SERVICE_DATE = date(2026, 1, 1)


def _claim(*lines):
    snap = snapshot(codes=["room_rent", "surgery", "consultation", "pharmacy", "diagnostics"])
    return adjudicate_claim(snap, list(lines), usage(), SERVICE_DATE)


def test_breach_scales_subject_charges_by_ratio():
    # room 8,000 -> capped 5,000, ratio 0.625; surgery & consultation scale.
    result = _claim(
        line("room_rent", "8000", ref="room"),
        line("surgery", "40000", ref="surgery"),
        line("consultation", "4000", ref="consult"),
    )
    by_ref = {li.ref: li for li in result.line_items}
    assert by_ref["surgery"].payable_amount == rupee("25000")  # 40000 * 0.625
    assert by_ref["consult"].payable_amount == rupee("2500")  # 4000 * 0.625
    for ref in ("surgery", "consult"):
        assert any(r.code is ReasonCode.PROPORTIONATE_DEDUCTION for r in by_ref[ref].reasons)


def test_irdai_excluded_categories_are_not_scaled():
    result = _claim(
        line("room_rent", "8000", ref="room"),
        line("pharmacy", "6000", ref="pharmacy"),
        line("diagnostics", "10000", ref="mri"),
    )
    by_ref = {li.ref: li for li in result.line_items}
    assert by_ref["pharmacy"].payable_amount == rupee("6000")
    assert by_ref["mri"].payable_amount == rupee("10000")
    for ref in ("pharmacy", "mri"):
        assert not any(r.code is ReasonCode.PROPORTIONATE_DEDUCTION for r in by_ref[ref].reasons)


def test_no_breach_means_no_proportionate_deduction():
    # room within its 5,000 cap -> nothing to scale.
    result = _claim(
        line("room_rent", "4000", ref="room"),
        line("surgery", "40000", ref="surgery"),
    )
    by_ref = {li.ref: li for li in result.line_items}
    assert by_ref["surgery"].payable_amount == rupee("40000")
    assert by_ref["surgery"].status is LineItemStatus.APPROVED


def test_proportionate_and_deductible_combine():
    # Proportionate (Pass B) then deductible (Pass D): surgery scales to 25,000 and is
    # untouched by the deductible; the ₹2,000 deductible is absorbed by the first line.
    snap = snapshot(deductible="2000", codes=["room_rent", "surgery"])
    result = adjudicate_claim(
        snap,
        [line("room_rent", "8000", ref="room"), line("surgery", "40000", ref="surgery")],
        usage(),
        SERVICE_DATE,
    )
    by_ref = {li.ref: li for li in result.line_items}
    assert by_ref["surgery"].payable_amount == rupee("25000")  # 40000 * 0.625
    assert by_ref["room"].payable_amount == rupee("3000")  # 5000 cap - 2000 deductible


def test_ratio_uses_billed_room_rent_not_capped_value():
    # ratio must be cap/billed = 5000/8000 = 0.625, not cap/cap.
    result = _claim(
        line("room_rent", "8000", ref="room"),
        line("surgery", "10000", ref="surgery"),
    )
    surgery = next(li for li in result.line_items if li.ref == "surgery")
    assert surgery.payable_amount == rupee("6250")  # 10000 * 0.625

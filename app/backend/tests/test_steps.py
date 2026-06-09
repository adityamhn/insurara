"""One test per pipeline step (SPEC §4.2), each asserting a domain rule — the reason
code emitted and the resulting payable/status — not just a return type. Proportionate
deduction has its own file (test_proportionate.py)."""

from datetime import date

from claims.domain.enums import LineItemStatus, ReasonCode
from claims.domain.money import rupee
from claims.engine.pipeline import adjudicate_claim

from .helpers import line, snapshot, usage

# Well after every waiting period so the waiting check passes by default.
SERVICE_DATE = date(2026, 1, 1)


def _one(snap, ln, service_date=SERVICE_DATE, use=None):
    return adjudicate_claim(snap, [ln], use or usage(), service_date).line_items[0]


# 1. Coverage check -------------------------------------------------------------
def test_excluded_category_is_denied():
    li = _one(snapshot(codes=["cosmetic"]), line("cosmetic", "5000"))
    assert li.status is LineItemStatus.DENIED
    assert li.payable_amount == rupee("0")
    assert li.reasons[0].code is ReasonCode.EXCLUDED


def test_unknown_coverage_type_is_denied():
    li = _one(snapshot(codes=["surgery"]), line("teleportation", "5000"))
    assert li.status is LineItemStatus.DENIED
    assert li.reasons[0].code is ReasonCode.EXCLUDED


# 2. Waiting period -------------------------------------------------------------
def test_service_within_waiting_period_is_denied():
    # maternity has a 730-day wait; service 100 days after policy start.
    li = _one(
        snapshot(codes=["maternity"]),
        line("maternity", "50000"),
        service_date=date(2024, 4, 10),
    )
    assert li.status is LineItemStatus.DENIED
    assert li.reasons[0].code is ReasonCode.WAITING_PERIOD


def test_service_after_waiting_period_is_allowed():
    li = _one(
        snapshot(codes=["maternity"]),
        line("maternity", "50000"),
        service_date=date(2026, 6, 1),
    )
    assert li.status is LineItemStatus.APPROVED


# 3. Sub-limit cap --------------------------------------------------------------
def test_sub_limit_caps_payable_and_partially_approves():
    # room 1% of 5,00,000 = 5,000/day; billed 8,000 -> capped to 5,000.
    li = _one(snapshot(codes=["room_rent"]), line("room_rent", "8000"))
    assert li.status is LineItemStatus.PARTIALLY_APPROVED
    assert li.payable_amount == rupee("5000")
    sub_limit = next(r for r in li.reasons if r.code is ReasonCode.SUB_LIMIT)
    assert sub_limit.amount_delta == rupee("-3000")


def test_sub_limit_per_day_scales_with_service_days():
    li = _one(
        snapshot(codes=["room_rent"]),
        line("room_rent", "18000", days=3),  # cap 5,000 x 3 = 15,000
    )
    assert li.payable_amount == rupee("15000")


# 5. Sum-insured / per-year sub-limit balance -----------------------------------
def test_sum_insured_exhausted_denies():
    snap = snapshot(sum_insured="500000", codes=["surgery"])
    li = _one(snap, line("surgery", "20000"), use=usage(si_consumed="500000"))
    assert li.status is LineItemStatus.DENIED
    assert li.reasons[-1].code is ReasonCode.SUM_INSURED_EXHAUSTED


def test_sum_insured_partial_balance_reduces():
    snap = snapshot(sum_insured="500000", codes=["surgery"])
    li = _one(snap, line("surgery", "20000"), use=usage(si_consumed="490000"))
    assert li.status is LineItemStatus.PARTIALLY_APPROVED
    assert li.payable_amount == rupee("10000")
    assert any(r.code is ReasonCode.SUM_INSURED_EXHAUSTED for r in li.reasons)


def test_per_year_sub_limit_exhausted_denies():
    # dental annual sub-limit 10,000, already 10,000 consumed.
    snap = snapshot(codes=["dental"])
    li = _one(
        snap,
        line("dental", "4000"),
        use=usage(sub_limit_consumed={"dental": "10000"}),
    )
    assert li.status is LineItemStatus.DENIED
    assert any(r.code is ReasonCode.SUB_LIMIT_EXHAUSTED for r in li.reasons)


def test_per_year_sub_limit_partial_balance_reduces():
    snap = snapshot(codes=["dental"])
    li = _one(
        snap,
        line("dental", "4000"),
        use=usage(sub_limit_consumed={"dental": "7000"}),
    )
    assert li.payable_amount == rupee("3000")  # only 10,000 - 7,000 remains


def test_per_year_sub_limit_threads_across_lines_in_one_claim():
    # Two dental lines in one claim must share the annual bucket: 7,000 remains
    # (10,000 cap - 3,000 prior), so 5,000 + 5,000 -> 5,000 + 2,000, not 5,000 + 5,000.
    snap = snapshot(codes=["dental"])
    result = adjudicate_claim(
        snap,
        [line("dental", "5000", ref="d1"), line("dental", "5000", ref="d2")],
        usage(sub_limit_consumed={"dental": "3000"}),
        SERVICE_DATE,
    )
    by_ref = {li.ref: li for li in result.line_items}
    assert by_ref["d1"].payable_amount == rupee("5000")
    assert by_ref["d2"].payable_amount == rupee("2000")


# 6. Deductible -----------------------------------------------------------------
def test_deductible_absorbed_before_payout():
    snap = snapshot(deductible="5000", codes=["surgery"])
    li = _one(snap, line("surgery", "20000"))
    assert li.payable_amount == rupee("15000")
    ded = next(r for r in li.reasons if r.code is ReasonCode.DEDUCTIBLE)
    assert ded.amount_delta == rupee("-5000")


def test_deductible_applied_once_across_lines():
    snap = snapshot(deductible="5000", codes=["surgery", "pharmacy"])
    result = adjudicate_claim(
        snap,
        [line("surgery", "20000", ref="s"), line("pharmacy", "4000", ref="p")],
        usage(),
        SERVICE_DATE,
    )
    # 5,000 deductible consumed entirely by the first line; second line untouched.
    total_ded = sum(
        -r.amount_delta
        for li in result.line_items
        for r in li.reasons
        if r.code is ReasonCode.DEDUCTIBLE
    )
    assert total_ded == rupee("5000")
    assert result.totals.total_payable == rupee("19000")


# 7. Co-payment -----------------------------------------------------------------
def test_copay_reduces_payable():
    snap = snapshot(copay_percent="20", codes=["surgery"])
    li = _one(snap, line("surgery", "10000"))
    assert li.status is LineItemStatus.PARTIALLY_APPROVED
    assert li.payable_amount == rupee("8000")
    copay = next(r for r in li.reasons if r.code is ReasonCode.COPAY)
    assert copay.amount_delta == rupee("-2000")


# 8. Needs-review ---------------------------------------------------------------
def test_high_value_line_routes_to_review():
    snap = snapshot(review_threshold="100000", codes=["surgery"])
    li = _one(snap, line("surgery", "150000"))
    assert li.status is LineItemStatus.UNDER_REVIEW
    assert li.payable_amount == rupee("0")
    assert li.reasons[0].code is ReasonCode.NEEDS_REVIEW


def test_exclusion_takes_precedence_over_review():
    # An excluded high-value line is a clear denial, not a review.
    snap = snapshot(review_threshold="100000", codes=["cosmetic"])
    li = _one(snap, line("cosmetic", "150000"))
    assert li.status is LineItemStatus.DENIED


def test_review_threshold_is_configurable():
    # A higher threshold lets a ₹1,50,000 line auto-adjudicate instead of routing.
    snap = snapshot(review_threshold="200000", codes=["surgery"])
    li = _one(snap, line("surgery", "150000"))
    assert li.status is LineItemStatus.APPROVED


# 9. Finalize -------------------------------------------------------------------
def test_full_approval_when_nothing_reduces():
    li = _one(snapshot(codes=["surgery"]), line("surgery", "20000"))
    assert li.status is LineItemStatus.APPROVED
    assert li.payable_amount == rupee("20000")
    assert li.reasons == []  # a clean approval emits no deduction reasons

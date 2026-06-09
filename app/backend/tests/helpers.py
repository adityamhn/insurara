"""Test builders for engine unit tests. Keep snapshots explicit and minimal so each
test reads as a domain statement, not ORM setup."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from claims.domain.enums import SubLimitBasis, SubLimitType
from claims.domain.models import (
    CoverageTypeRule,
    LineItemInput,
    PolicySnapshot,
    UsageCounters,
)

POLICY_START = date(2024, 1, 1)

# A catalogue of coverage-type rules mirroring the SPEC seed semantics.
RULES: dict[str, CoverageTypeRule] = {
    "room_rent": CoverageTypeRule(
        code="room_rent",
        name="Room rent",
        sub_limit_type=SubLimitType.PERCENT_OF_SI,
        sub_limit_value=Decimal("1"),  # 1% of SI per day
        sub_limit_basis=SubLimitBasis.PER_DAY,
        triggers_proportionate_deduction=True,
        subject_to_proportionate_deduction=False,
    ),
    "surgery": CoverageTypeRule(
        code="surgery", name="Surgery", subject_to_proportionate_deduction=True
    ),
    "consultation": CoverageTypeRule(
        code="consultation",
        name="Consultation",
        subject_to_proportionate_deduction=True,
    ),
    # IRDAI 2024: pharmacy & diagnostics are NOT subject to proportionate deduction.
    "pharmacy": CoverageTypeRule(
        code="pharmacy", name="Pharmacy", subject_to_proportionate_deduction=False
    ),
    "diagnostics": CoverageTypeRule(
        code="diagnostics", name="Diagnostics", subject_to_proportionate_deduction=False
    ),
    "cosmetic": CoverageTypeRule(code="cosmetic", name="Cosmetic surgery", covered=False),
    "maternity": CoverageTypeRule(code="maternity", name="Maternity", waiting_period_days=730),
    # A per-year absolute sub-limit category, for exhaustion tests.
    "dental": CoverageTypeRule(
        code="dental",
        name="Dental",
        sub_limit_type=SubLimitType.ABSOLUTE,
        sub_limit_value=Decimal("10000"),
        sub_limit_basis=SubLimitBasis.PER_YEAR,
    ),
}


def snapshot(
    *,
    sum_insured: str = "500000",
    deductible: str = "0",
    copay_percent: str = "0",
    codes: list[str] | None = None,
    review_threshold: str = "100000",
) -> PolicySnapshot:
    chosen = codes or list(RULES.keys())
    return PolicySnapshot(
        policy_number="POL-TEST-001",
        start_date=POLICY_START,
        sum_insured=Decimal(sum_insured),
        deductible=Decimal(deductible),
        copay_percent=Decimal(copay_percent),
        coverage_types={c: RULES[c] for c in chosen},
        high_value_review_threshold=Decimal(review_threshold),
    )


def line(code: str, billed: str, *, ref: str | None = None, days: int = 1) -> LineItemInput:
    return LineItemInput(
        ref=ref or code,
        coverage_type_code=code,
        billed_amount=Decimal(billed),
        service_days=days,
    )


def usage(
    *,
    si_consumed: str = "0",
    deductible_consumed: str = "0",
    sub_limit_consumed: dict[str, str] | None = None,
) -> UsageCounters:
    return UsageCounters(
        sum_insured_consumed=Decimal(si_consumed),
        deductible_consumed=Decimal(deductible_consumed),
        sub_limit_consumed={k: Decimal(v) for k, v in (sub_limit_consumed or {}).items()},
    )

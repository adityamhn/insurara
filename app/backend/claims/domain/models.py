"""Pure domain DTOs — no DB, no HTTP. These are what the adjudication engine reads
and returns. Persistence maps these to/from ORM rows; the engine never
sees the ORM.

Money fields are Decimal. The engine quantizes to 2dp via `domain.money`; inputs are
accepted as Decimal/int/str (floats are refused at the money boundary).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from .enums import (
    ClaimStage,
    ClaimStatus,
    LineItemStatus,
    PipelineStep,
    ReasonCode,
    SubLimitBasis,
    SubLimitType,
)


class CoverageTypeRule(BaseModel):
    """One category of covered expense and its rules. This is the
    decision-table row — the configurable per-category `what`."""

    model_config = ConfigDict(frozen=True)

    code: str
    name: str
    covered: bool = True
    sub_limit_type: SubLimitType = SubLimitType.NONE
    sub_limit_value: Decimal | None = None
    sub_limit_basis: SubLimitBasis = SubLimitBasis.PER_CLAIM
    waiting_period_days: int = 0
    triggers_proportionate_deduction: bool = False
    subject_to_proportionate_deduction: bool = False


class PolicySnapshot(BaseModel):
    """Frozen policy terms the engine adjudicates against. Captured at
    claim creation so later policy edits never change a past claim. Usage counters
    are passed separately (they change on settlement, not at adjudication)."""

    model_config = ConfigDict(frozen=True)

    policy_number: str
    start_date: date
    sum_insured: Decimal
    deductible: Decimal = Decimal("0")
    copay_percent: Decimal = Decimal("0")
    # Coverage rules keyed by code for O(1) lookup during the coverage check.
    coverage_types: dict[str, CoverageTypeRule]
    # Auto-vs-human split: line items billed above this route to review.
    high_value_review_threshold: Decimal = Decimal("100000")


class UsageCounters(BaseModel):
    """Running consumption for a policy-year. Snapshotted at claim
    creation, incremented on settlement. The engine treats these as read-only."""

    sum_insured_consumed: Decimal = Decimal("0")
    deductible_consumed: Decimal = Decimal("0")
    # Per-coverage-type consumed, keyed by coverage_type_code (for per_year sub-limits).
    sub_limit_consumed: dict[str, Decimal] = Field(default_factory=dict)


class LineItemInput(BaseModel):
    """A single billed expense submitted on a claim."""

    # Caller-supplied stable handle so results can be matched back (line ordinal in
    # practice). Sensitive fields are carried but not protected.
    ref: str
    coverage_type_code: str
    billed_amount: Decimal
    service_days: int = 1  # for per_day sub-limit caps (default single-day)
    diagnosis_code: str | None = None  # SENSITIVE
    provider_name: str | None = None  # SENSITIVE
    description: str | None = None


class Reason(BaseModel):
    """A structured explanation fragment emitted by a pipeline step.
    The ordered list of Reasons per line item *is* the EOB / deduction waterfall."""

    code: ReasonCode
    message: str
    amount_delta: Decimal  # how much this step reduced the payable (<= 0); 0 if none
    step: PipelineStep


class LineItemResult(BaseModel):
    """Outcome of adjudicating one line item."""

    ref: str
    coverage_type_code: str
    billed_amount: Decimal
    payable_amount: Decimal
    status: LineItemStatus
    reasons: list[Reason] = Field(default_factory=list)

    @property
    def member_share(self) -> Decimal:
        return self.billed_amount - self.payable_amount


class ClaimTotals(BaseModel):
    total_billed: Decimal
    total_payable: Decimal
    total_member_borne: Decimal


class ClaimResult(BaseModel):
    """Outcome of adjudicating a whole claim: per-line results plus the derived
    claim stage/status and rolled-up totals."""

    line_items: list[LineItemResult]
    status: ClaimStatus
    stage: ClaimStage
    totals: ClaimTotals

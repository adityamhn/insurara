"""Domain enums. Status is only ever represented by these — never bare strings
(SPEC §3.4). String-valued so they serialize cleanly to JSON/DB later.
"""

from enum import Enum


class LineItemStatus(str, Enum):
    """The state machine of the unit that actually gets adjudicated (SPEC §3.4)."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    PAID = "paid"
    DISPUTED = "disputed"


class ClaimStage(str, Enum):
    """Coarse lifecycle position of a claim (SPEC §3.4, first axis)."""

    SUBMITTED = "submitted"
    UNDER_ADJUDICATION = "under_adjudication"
    DECIDED = "decided"
    SETTLED = "settled"
    CLOSED = "closed"


class ClaimStatus(str, Enum):
    """Claim decision outcome, DERIVED from line items (SPEC §3.4, second axis)."""

    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    NEEDS_REVIEW = "needs_review"


class DisputeState(str, Enum):
    """Dispute lifecycle (SPEC §3.2). Used by milestone 5; defined here so the
    domain vocabulary lives in one place."""

    RAISED = "raised"
    UNDER_REVIEW = "under_review"
    UPHELD = "upheld"
    OVERTURNED = "overturned"


class SubLimitType(str, Enum):
    """How a coverage type's per-category cap is expressed (SPEC §3.2)."""

    NONE = "none"
    ABSOLUTE = "absolute"
    PERCENT_OF_SI = "percent_of_si"


class SubLimitBasis(str, Enum):
    """The period a sub-limit applies over (SPEC §3.2)."""

    PER_DAY = "per_day"
    PER_CLAIM = "per_claim"
    PER_YEAR = "per_year"


class ReasonCode(str, Enum):
    """Machine codes for every pipeline step that can change an outcome.
    The accumulated Reasons are the EOB (SPEC Decision 6)."""

    EXCLUDED = "EXCLUDED"
    WAITING_PERIOD = "WAITING_PERIOD"
    SUB_LIMIT = "SUB_LIMIT"
    PROPORTIONATE_DEDUCTION = "PROPORTIONATE_DEDUCTION"
    SUB_LIMIT_EXHAUSTED = "SUB_LIMIT_EXHAUSTED"
    SUM_INSURED_EXHAUSTED = "SUM_INSURED_EXHAUSTED"
    DEDUCTIBLE = "DEDUCTIBLE"
    COPAY = "COPAY"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REVIEW_RESOLVED = "REVIEW_RESOLVED"  # human adjuster resolved an under_review line


class PipelineStep(str, Enum):
    """Which pipeline stage emitted a Reason (SPEC §4.2). Lets the UI group the
    waterfall and order reasons stably."""

    COVERAGE = "coverage"
    WAITING_PERIOD = "waiting_period"
    SUB_LIMIT = "sub_limit"
    PROPORTIONATE_DEDUCTION = "proportionate_deduction"
    BALANCE = "balance"
    DEDUCTIBLE = "deductible"
    COPAY = "copay"
    NEEDS_REVIEW = "needs_review"

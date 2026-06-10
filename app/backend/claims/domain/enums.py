"""Domain enums. Status is only ever represented by these — never bare strings
. String-valued so they serialize cleanly to JSON/DB later.
"""

from enum import Enum


class LineItemStatus(str, Enum):
    """The state machine of the unit that actually gets adjudicated."""

    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    PAID = "paid"
    DISPUTED = "disputed"


class ClaimStage(str, Enum):
    """Coarse lifecycle position of a claim."""

    SUBMITTED = "submitted"
    UNDER_ADJUDICATION = "under_adjudication"
    DECIDED = "decided"
    SETTLED = "settled"
    CLOSED = "closed"


class ClaimStatus(str, Enum):
    """Claim decision outcome, DERIVED from line items."""

    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    DENIED = "denied"
    NEEDS_REVIEW = "needs_review"


class PolicyStatus(str, Enum):
    """Policy lifecycle — only an in-force policy accepts new claims."""

    IN_FORCE = "in_force"
    LAPSED = "lapsed"


class DisputeState(str, Enum):
    """Dispute lifecycle. Defined here so the domain vocabulary lives in one place."""

    RAISED = "raised"
    UNDER_REVIEW = "under_review"
    UPHELD = "upheld"
    OVERTURNED = "overturned"


class SubLimitType(str, Enum):
    """How a coverage type's per-category cap is expressed."""

    NONE = "none"
    ABSOLUTE = "absolute"
    PERCENT_OF_SI = "percent_of_si"


class SubLimitBasis(str, Enum):
    """The period a sub-limit applies over."""

    PER_DAY = "per_day"
    PER_CLAIM = "per_claim"
    PER_YEAR = "per_year"


class ReasonCode(str, Enum):
    """Machine codes for every pipeline step that can change an outcome.
    The accumulated Reasons are the EOB."""

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
    DISPUTE_OVERTURNED = "DISPUTE_OVERTURNED"  # a dispute changed a line's decision


class PipelineStep(str, Enum):
    """Which pipeline stage emitted a Reason. Lets the UI group the
    waterfall and order reasons stably."""

    COVERAGE = "coverage"
    WAITING_PERIOD = "waiting_period"
    SUB_LIMIT = "sub_limit"
    PROPORTIONATE_DEDUCTION = "proportionate_deduction"
    BALANCE = "balance"
    DEDUCTIBLE = "deductible"
    COPAY = "copay"
    NEEDS_REVIEW = "needs_review"

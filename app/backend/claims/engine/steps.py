"""The per-line pipeline steps (SPEC §4.2), each a pure function `step(ctx) -> StepResult`.

Steps run in the order the orchestrator calls them; `payable` starts at `billed_amount`
and is threaded through. A step may short-circuit by returning a `terminal_status`
(e.g. exclusion → DENIED). Each step that changes the outcome emits a Reason — those
Reasons accumulate into the EOB (Decision 6).

Cross-line steps (proportionate deduction, deductible, sum-insured/sub-limit balance)
are NOT here — they live in `pipeline.py` because they need the whole claim (SPEC §4.3).
"""

from __future__ import annotations

from decimal import Decimal

from ..domain.enums import (
    LineItemStatus,
    PipelineStep,
    ReasonCode,
    SubLimitBasis,
    SubLimitType,
)
from ..domain.models import Reason
from ..domain.money import ZERO, quantize, rupee
from .context import AdjudicationContext, StepResult


def _rupees(amount: Decimal) -> str:
    """Format an amount for human-readable Reason messages, e.g. ₹5,000.00."""
    return f"₹{amount:,.2f}"


def step_coverage(ctx: AdjudicationContext) -> StepResult:
    """1. Coverage check. Unknown coverage type or `covered == false` → DENIED."""
    rule = ctx.rule
    if rule is None or not rule.covered:
        label = rule.name if rule else ctx.line.coverage_type_code
        return StepResult(
            payable=ZERO,
            terminal_status=LineItemStatus.DENIED,
            reasons=[
                Reason(
                    code=ReasonCode.EXCLUDED,
                    message=f"Service type '{label}' is not covered under this policy.",
                    amount_delta=-ctx.payable,
                    step=PipelineStep.COVERAGE,
                )
            ],
        )
    return StepResult(payable=ctx.payable)


def step_waiting_period(ctx: AdjudicationContext) -> StepResult:
    """2. Waiting period. Service before the category's waiting period → DENIED."""
    rule = ctx.rule
    assert rule is not None  # coverage step guarantees this
    if rule.waiting_period_days <= 0:
        return StepResult(payable=ctx.payable)

    active_days = (ctx.service_date - ctx.snapshot.start_date).days
    if active_days < rule.waiting_period_days:
        return StepResult(
            payable=ZERO,
            terminal_status=LineItemStatus.DENIED,
            reasons=[
                Reason(
                    code=ReasonCode.WAITING_PERIOD,
                    message=(
                        f"This service has a {rule.waiting_period_days}-day waiting "
                        f"period; the policy was active only {active_days} days at the "
                        "time of service."
                    ),
                    amount_delta=-ctx.payable,
                    step=PipelineStep.WAITING_PERIOD,
                )
            ],
        )
    return StepResult(payable=ctx.payable)


def step_needs_review(ctx: AdjudicationContext) -> StepResult:
    """8 (applied early). Auto-vs-human split (Decision 9): a line billed above the
    high-value threshold can't be auto-decided → route to UNDER_REVIEW.

    Placed after the hard denials (coverage/waiting) but before the money reductions:
    a reviewer re-decides the whole line, so running it through caps/copay first would
    only produce reasons that get discarded. Documented deviation from §4.2's ordinal.
    """
    threshold = ctx.snapshot.high_value_review_threshold
    if ctx.line.billed_amount > threshold:
        return StepResult(
            payable=ctx.payable,
            terminal_status=LineItemStatus.UNDER_REVIEW,
            reasons=[
                Reason(
                    code=ReasonCode.NEEDS_REVIEW,
                    message=(
                        f"Routed for manual review: billed {_rupees(ctx.line.billed_amount)} "
                        f"exceeds the {_rupees(threshold)} auto-adjudication threshold."
                    ),
                    amount_delta=ZERO,
                    step=PipelineStep.NEEDS_REVIEW,
                )
            ],
        )
    return StepResult(payable=ctx.payable)


def _sub_limit_cap(ctx: AdjudicationContext) -> Decimal | None:
    """Compute the absolute rupee cap for this line's sub-limit, or None if uncapped."""
    rule = ctx.rule
    assert rule is not None
    if rule.sub_limit_type is SubLimitType.NONE or rule.sub_limit_value is None:
        return None

    if rule.sub_limit_type is SubLimitType.ABSOLUTE:
        base = rule.sub_limit_value
    else:  # PERCENT_OF_SI
        base = ctx.snapshot.sum_insured * rule.sub_limit_value / Decimal("100")

    if rule.sub_limit_basis is SubLimitBasis.PER_DAY:
        base = base * Decimal(ctx.line.service_days)
    return quantize(base)


def step_sub_limit_cap(ctx: AdjudicationContext) -> StepResult:
    """3. Sub-limit cap. If payable exceeds the per-category cap, cap it, record the
    excess, and flag the line as breached. A room_rent breach also carries the ratio
    that drives the claim-level proportionate-deduction pass (§4.3)."""
    cap = _sub_limit_cap(ctx)
    if cap is None or ctx.payable <= cap:
        return StepResult(payable=ctx.payable)

    rule = ctx.rule
    assert rule is not None
    excess = ctx.payable - cap
    ratio = None
    if rule.triggers_proportionate_deduction:
        # ratio off the *billed* room rent, per §4.4 (5000/8000 = 0.625).
        ratio = cap / ctx.line.billed_amount

    return StepResult(
        payable=cap,
        breached_sub_limit=True,
        proportionate_ratio=ratio,
        reasons=[
            Reason(
                code=ReasonCode.SUB_LIMIT,
                message=(
                    f"{rule.name} is capped at {_rupees(cap)}; billed "
                    f"{_rupees(ctx.payable)}; {_rupees(excess)} exceeds the sub-limit."
                ),
                amount_delta=-excess,
                step=PipelineStep.SUB_LIMIT,
            )
        ],
    )


def step_copay(ctx: AdjudicationContext) -> StepResult:
    """7. Co-payment. The member bears `copay_percent%` of the remaining payable."""
    pct = ctx.snapshot.copay_percent
    if pct <= 0 or ctx.payable <= ZERO:
        return StepResult(payable=ctx.payable)

    member_share = quantize(ctx.payable * pct / Decimal("100"))
    new_payable = rupee(ctx.payable - member_share)
    return StepResult(
        payable=new_payable,
        reasons=[
            Reason(
                code=ReasonCode.COPAY,
                message=(f"{pct:g}% co-payment ({_rupees(member_share)}) is borne by the member."),
                amount_delta=-member_share,
                step=PipelineStep.COPAY,
            )
        ],
    )

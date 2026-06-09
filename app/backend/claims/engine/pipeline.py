"""Claim-level orchestration (SPEC §4.3).

`adjudicate_claim` is the engine's public entry point: given a frozen policy snapshot,
the line items, the usage counters, and the service date, it returns a fully decided
`ClaimResult` — per-line payable + ordered Reasons, the derived claim stage/status, and
totals. Pure and DB-free.

Pass order (honours §4.2's sequence while respecting that some steps are cross-line, §4.3):
  A. per-line   : coverage → waiting → needs-review → sub-limit cap   (short-circuit on terminal)
  B. claim-level: proportionate deduction
  C. claim-level: sum-insured / per-year sub-limit balance  (threads in-claim consumption)
  D. claim-level: deductible (applied once across the claim)
  E. per-line   : co-payment
  F. per-line   : finalize (status from payable vs billed)
  G. claim-level: derive claim status + stage from line states (§3.4)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..domain.enums import (
    LineItemStatus,
    PipelineStep,
    ReasonCode,
    SubLimitBasis,
    SubLimitType,
)
from ..domain.models import (
    ClaimResult,
    ClaimTotals,
    LineItemInput,
    LineItemResult,
    PolicySnapshot,
    Reason,
    UsageCounters,
)
from ..domain.money import ZERO, quantize, rupee
from ..domain.state_machine import derive_claim_state
from .context import AdjudicationContext, StepResult
from .steps import (
    _rupees,
    step_copay,
    step_coverage,
    step_needs_review,
    step_sub_limit_cap,
    step_waiting_period,
)

# Per-line steps run in order until one short-circuits to a terminal status (Pass A).
_PER_LINE_STEPS = (
    step_coverage,
    step_waiting_period,
    step_needs_review,
    step_sub_limit_cap,
)


def adjudicate_claim(
    snapshot: PolicySnapshot,
    line_items: list[LineItemInput],
    usage: UsageCounters,
    service_date: date,
) -> ClaimResult:
    """Adjudicate a whole claim against a frozen snapshot. The one function the web
    layer calls; everything below it is a private pass."""
    if not line_items:
        raise ValueError("a claim must have at least one line item")

    contexts = [_build_context(li, snapshot, usage, service_date) for li in line_items]

    # Pass A — per-line steps, short-circuiting on the first terminal decision.
    for ctx in contexts:
        for step in _PER_LINE_STEPS:
            _apply(ctx, step(ctx))
            if ctx.is_terminal:
                break

    _proportionate_pass(contexts)  # Pass B
    _balance_pass(contexts, snapshot, usage)  # Pass C
    _deductible_pass(contexts, snapshot, usage)  # Pass D

    # Pass E — co-payment per (still non-terminal) line.
    for ctx in contexts:
        if not ctx.is_terminal:
            _apply(ctx, step_copay(ctx))

    results = [_finalize(ctx) for ctx in contexts]  # Pass F
    status, stage = derive_claim_state([r.status for r in results])  # Pass G
    return ClaimResult(line_items=results, status=status, stage=stage, totals=_totals(results))


# --------------------------------------------------------------------------- #
# Context plumbing
# --------------------------------------------------------------------------- #
def _build_context(
    line: LineItemInput,
    snapshot: PolicySnapshot,
    usage: UsageCounters,
    service_date: date,
) -> AdjudicationContext:
    return AdjudicationContext(
        line=line,
        rule=snapshot.coverage_types.get(line.coverage_type_code),
        snapshot=snapshot,
        usage=usage,
        service_date=service_date,
        payable=rupee(line.billed_amount),
    )


def _apply(ctx: AdjudicationContext, result: StepResult) -> None:
    """Fold a per-line StepResult back into the working context."""
    ctx.payable = result.payable
    ctx.reasons.extend(result.reasons)
    if result.breached_sub_limit:
        ctx.breached_sub_limit = True
    if result.proportionate_ratio is not None:
        ctx.proportionate_ratio = result.proportionate_ratio
    if result.terminal_status is not None:
        ctx.terminal_status = result.terminal_status


# --------------------------------------------------------------------------- #
# Pass B — proportionate deduction (Indian-specific, §4.3)
# --------------------------------------------------------------------------- #
def _proportionate_pass(contexts: list[AdjudicationContext]) -> None:
    """If a line that *triggers* proportionate deduction (room_rent) breached its
    sub-limit, scale every *other* line that is *subject* to it by
    ratio = cap / billed_room_rent. IRDAI-2024 exclusions (pharmacy/implants/
    diagnostics) carry `subject=False` in the seed, so they're skipped — the rule is
    data-driven, never a hardcoded category list."""
    trigger = next(
        (
            c
            for c in contexts
            if not c.is_terminal
            and c.rule is not None
            and c.rule.triggers_proportionate_deduction
            and c.breached_sub_limit
            and c.proportionate_ratio is not None
        ),
        None,
    )
    if trigger is None:
        return

    ratio: Decimal = trigger.proportionate_ratio  # type: ignore[assignment]
    for ctx in contexts:
        if ctx is trigger or ctx.is_terminal or ctx.payable <= ZERO:
            continue
        if ctx.rule is None or not ctx.rule.subject_to_proportionate_deduction:
            continue
        new_payable = quantize(ctx.payable * ratio)
        delta = new_payable - ctx.payable
        ctx.reasons.append(
            Reason(
                code=ReasonCode.PROPORTIONATE_DEDUCTION,
                message=(
                    f"Room rent exceeded its sub-limit (ratio {ratio.normalize():f}); "
                    "associated charges reduced proportionately."
                ),
                amount_delta=delta,
                step=PipelineStep.PROPORTIONATE_DEDUCTION,
            )
        )
        ctx.payable = new_payable


# --------------------------------------------------------------------------- #
# Pass C — sum-insured / per-year sub-limit balance (§4.2 step 5)
# --------------------------------------------------------------------------- #
def _annual_cap(ctx: AdjudicationContext) -> Decimal:
    """The per-year sub-limit value in rupees (no per-day multiplier)."""
    rule = ctx.rule
    assert rule is not None and rule.sub_limit_value is not None
    if rule.sub_limit_type is SubLimitType.ABSOLUTE:
        return quantize(rule.sub_limit_value)
    return quantize(ctx.snapshot.sum_insured * rule.sub_limit_value / Decimal("100"))


def _balance_pass(
    contexts: list[AdjudicationContext],
    snapshot: PolicySnapshot,
    usage: UsageCounters,
) -> None:
    """Reduce each line to the remaining per-year sub-limit and remaining sum insured,
    threading consumption *within this claim* so a claim can't exceed a limit by
    splitting it across lines. Exhaustion → DENIED. Order per line: per-year sub-limit
    first, then sum insured (§4.2)."""
    remaining_si = snapshot.sum_insured - usage.sum_insured_consumed
    remaining_sub: dict[str, Decimal] = {}

    for ctx in contexts:
        if ctx.is_terminal or ctx.payable <= ZERO:
            continue
        rule = ctx.rule
        assert rule is not None

        # Per-year sub-limit balance (only categories with a per_year sub-limit).
        if (
            rule.sub_limit_type is not SubLimitType.NONE
            and rule.sub_limit_basis is SubLimitBasis.PER_YEAR
        ):
            code = rule.code
            if code not in remaining_sub:
                remaining_sub[code] = _annual_cap(ctx) - usage.sub_limit_consumed.get(code, ZERO)
            if remaining_sub[code] <= ZERO:
                _deny_exhausted(
                    ctx,
                    ReasonCode.SUB_LIMIT_EXHAUSTED,
                    PipelineStep.BALANCE,
                    f"The annual sub-limit for {rule.name} is exhausted; nothing remains.",
                )
                continue
            if ctx.payable > remaining_sub[code]:
                excess = ctx.payable - remaining_sub[code]
                ctx.reasons.append(
                    Reason(
                        code=ReasonCode.SUB_LIMIT_EXHAUSTED,
                        message=(
                            f"Only {_rupees(remaining_sub[code])} of the annual "
                            f"{rule.name} sub-limit remains; {_rupees(excess)} is not payable."
                        ),
                        amount_delta=-excess,
                        step=PipelineStep.BALANCE,
                    )
                )
                ctx.payable = remaining_sub[code]
            remaining_sub[code] -= ctx.payable

        # Sum-insured balance.
        if remaining_si <= ZERO:
            _deny_exhausted(
                ctx,
                ReasonCode.SUM_INSURED_EXHAUSTED,
                PipelineStep.BALANCE,
                "The policy's sum insured is exhausted; nothing remains for this service.",
            )
            continue
        if ctx.payable > remaining_si:
            excess = ctx.payable - remaining_si
            ctx.reasons.append(
                Reason(
                    code=ReasonCode.SUM_INSURED_EXHAUSTED,
                    message=(
                        f"Only {_rupees(remaining_si)} of the sum insured remains; "
                        f"{_rupees(excess)} is not payable."
                    ),
                    amount_delta=-excess,
                    step=PipelineStep.BALANCE,
                )
            )
            ctx.payable = remaining_si
        remaining_si -= ctx.payable


def _deny_exhausted(
    ctx: AdjudicationContext,
    code: ReasonCode,
    step: PipelineStep,
    message: str,
) -> None:
    ctx.reasons.append(Reason(code=code, message=message, amount_delta=-ctx.payable, step=step))
    ctx.payable = ZERO
    ctx.terminal_status = LineItemStatus.DENIED


# --------------------------------------------------------------------------- #
# Pass D — deductible, applied once across the claim (§4.3)
# --------------------------------------------------------------------------- #
def _deductible_pass(
    contexts: list[AdjudicationContext],
    snapshot: PolicySnapshot,
    usage: UsageCounters,
) -> None:
    remaining = snapshot.deductible - usage.deductible_consumed
    if remaining <= ZERO:
        return
    for ctx in contexts:
        if ctx.is_terminal or ctx.payable <= ZERO or remaining <= ZERO:
            continue
        absorbed = min(ctx.payable, remaining)
        ctx.reasons.append(
            Reason(
                code=ReasonCode.DEDUCTIBLE,
                message=f"{_rupees(absorbed)} applied toward the annual deductible.",
                amount_delta=-absorbed,
                step=PipelineStep.DEDUCTIBLE,
            )
        )
        ctx.payable = ctx.payable - absorbed
        remaining -= absorbed


# --------------------------------------------------------------------------- #
# Pass F/G — finalize and roll up
# --------------------------------------------------------------------------- #
def _finalize(ctx: AdjudicationContext) -> LineItemResult:
    if ctx.terminal_status is not None:
        # Terminal here is only DENIED or UNDER_REVIEW — neither has a payout:
        # denied pays nothing, under_review is decided later by a human.
        status = ctx.terminal_status
        payable = ZERO
    else:
        billed = rupee(ctx.line.billed_amount)
        if ctx.payable >= billed:
            status = LineItemStatus.APPROVED
        elif ctx.payable <= ZERO:
            status = LineItemStatus.DENIED
        else:
            status = LineItemStatus.PARTIALLY_APPROVED
        payable = ctx.payable

    return LineItemResult(
        ref=ctx.line.ref,
        coverage_type_code=ctx.line.coverage_type_code,
        billed_amount=rupee(ctx.line.billed_amount),
        payable_amount=rupee(payable),
        status=status,
        reasons=ctx.reasons,
    )


def _totals(results: list[LineItemResult]) -> ClaimTotals:
    billed = sum((r.billed_amount for r in results), ZERO)
    payable = sum((r.payable_amount for r in results), ZERO)
    return ClaimTotals(
        total_billed=rupee(billed),
        total_payable=rupee(payable),
        total_member_borne=rupee(billed - payable),
    )

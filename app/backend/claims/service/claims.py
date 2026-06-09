"""Claim orchestration: submit → snapshot → adjudicate → persist → derive.

This service is the seam both the seed script and the FastAPI layer (milestone 3) call.
It wires the pure engine (milestone 1) to persistence (milestone 2): it never puts
business rules here — derivation and amounts come from the engine, this just persists
them and records the activity stream.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from ..domain.enums import (
    ClaimStage,
    DisputeState,
    LineItemStatus,
    PipelineStep,
    ReasonCode,
    SubLimitBasis,
    SubLimitType,
)
from ..domain.models import LineItemInput
from ..domain.money import ZERO, rupee
from ..domain.state_machine import derive_claim_state, transition
from ..engine.pipeline import adjudicate_claim
from ..persistence import models as orm
from .snapshot import load_snapshot_dtos, persist_snapshot


class ClaimError(ValueError):
    """Invalid claim submission (unknown policy/member, member not on policy, etc.)."""


class ClaimConflict(Exception):
    """A lifecycle action that conflicts with the claim's current state (→ HTTP 409),
    e.g. settling while a line item is still under review."""


def create_claim(
    session,
    *,
    policy_id: int,
    member_id: int,
    service_date: date,
    line_items: list[LineItemInput],
) -> orm.Claim:
    if not line_items:
        raise ClaimError("a claim must have at least one line item")

    policy = session.get(orm.Policy, policy_id)
    if policy is None:
        raise ClaimError(f"policy {policy_id} not found")
    if policy.status != "in_force":
        raise ClaimError(f"policy {policy.policy_number} is {policy.status}; cannot accept claims")
    if not (policy.start_date <= service_date <= policy.end_date):
        raise ClaimError(
            f"service date {service_date} is outside the policy period "
            f"({policy.start_date} to {policy.end_date})"
        )
    if not any(link.member_id == member_id for link in policy.members):
        raise ClaimError(f"member {member_id} is not insured on policy {policy_id}")

    # Freeze the terms this claim will forever be judged against.
    snapshot_row, snapshot_dto, usage_dto = persist_snapshot(session, policy)

    # Starts at stage `submitted`; the engine's derivation overwrites stage+status below.
    claim = orm.Claim(
        policy_id=policy.id,
        policy_snapshot_id=snapshot_row.id,
        member_id=member_id,
        service_date=service_date,
    )
    session.add(claim)
    session.flush()

    # Persist line items as submitted, with a stable ref the engine result maps back to.
    engine_inputs: list[LineItemInput] = []
    rows_by_ref: dict[str, orm.LineItem] = {}
    for i, li in enumerate(line_items):
        ref = str(i)
        engine_inputs.append(li.model_copy(update={"ref": ref}))
        row = orm.LineItem(
            claim_id=claim.id,
            ref=ref,
            coverage_type_code=li.coverage_type_code,
            billed_amount=li.billed_amount,
            service_days=li.service_days,
            diagnosis_code=li.diagnosis_code,
            provider_name=li.provider_name,
            description=li.description,
        )
        session.add(row)
        rows_by_ref[ref] = row

    result = adjudicate_claim(snapshot_dto, engine_inputs, usage_dto, service_date)

    # Fold the engine's decision back onto the rows.
    for li_result in result.line_items:
        row = rows_by_ref[li_result.ref]
        row.payable_amount = li_result.payable_amount
        row.status = li_result.status
        # Append via the relationship so the FK is set on flush (row.id is unassigned).
        for ordinal, reason in enumerate(li_result.reasons):
            row.reasons.append(
                orm.Reason(
                    ordinal=ordinal,
                    code=reason.code,
                    message=reason.message,
                    amount_delta=reason.amount_delta,
                    step=reason.step,
                )
            )

    claim.status = result.status
    claim.stage = result.stage

    _log(session, claim, f"Claim submitted with {len(line_items)} line item(s).")
    _log(
        session,
        claim,
        f"Adjudicated: {result.status.value} ({result.stage.value}); "
        f"billed ₹{result.totals.total_billed}, payable ₹{result.totals.total_payable}.",
    )

    session.flush()
    return claim


def resolve_review(
    session,
    claim: orm.Claim,
    *,
    line_item_id: int,
    decision: str,
    payable_amount: Decimal | None = None,
    note: str | None = None,
) -> orm.Claim:
    """Human adjuster resolves an under_review line item, then the claim re-derives
    (SPEC §5.3). This is the back half of the "3 covered, 1 denied, 1 needs review"
    loop: once the review is resolved the claim drops out of needs_review."""
    line = next((li for li in claim.line_items if li.id == line_item_id), None)
    if line is None:
        raise ClaimError(f"line item {line_item_id} is not on claim {claim.id}")
    if line.status is not LineItemStatus.UNDER_REVIEW:
        raise ClaimConflict(f"line item {line_item_id} is not under review")

    billed = line.billed_amount
    # The adjuster may confirm or reduce, never exceed, the rules-allowed amount the
    # engine already computed (caps/proportionate/copay) before routing to review.
    allowed = line.payable_amount
    if decision == "approve":
        new_payable = allowed
        new_status = (
            LineItemStatus.APPROVED if allowed >= billed else LineItemStatus.PARTIALLY_APPROVED
        )
        verb = f"approved the rules-allowed ₹{allowed}"
    elif decision == "partially_approve":
        if payable_amount is None or not (ZERO < payable_amount <= allowed):
            raise ClaimError(
                f"partially_approve requires 0 < payable_amount <= the rules-allowed ₹{allowed}"
            )
        new_payable = rupee(payable_amount)
        new_status, verb = (
            LineItemStatus.PARTIALLY_APPROVED,
            f"partially approved at ₹{new_payable}",
        )
    elif decision == "deny":
        new_status, new_payable, verb = LineItemStatus.DENIED, ZERO, "denied"
    else:
        raise ClaimError(f"unknown decision '{decision}'")

    line.status = transition(line.status, new_status)
    line.payable_amount = rupee(new_payable)
    line.reasons.append(
        orm.Reason(
            ordinal=len(line.reasons),
            code=ReasonCode.REVIEW_RESOLVED,
            message=f"Reviewer {verb}." + (f" Note: {note}" if note else ""),
            amount_delta=ZERO,
            step=PipelineStep.NEEDS_REVIEW,
        )
    )

    # Re-derive the claim from the new set of line-item states.
    status, stage = derive_claim_state([li.status for li in claim.line_items])
    claim.status, claim.stage = status, stage
    _log(session, claim, f"Review resolved on line {line.ref}: {verb}.", actor="adjuster")
    session.flush()
    return claim


def settle_claim(session, claim: orm.Claim) -> orm.Claim:
    """Pay out approved/partially-approved line items and increment the policy's live
    usage counters (SPEC §3.3, §5.3). Counters move on settlement, not adjudication.
    Guard: cannot settle while any line item is under review (→ 409)."""
    if claim.stage is ClaimStage.SETTLED:
        raise ClaimConflict(f"claim {claim.id} is already settled")
    if any(li.status is LineItemStatus.UNDER_REVIEW for li in claim.line_items):
        raise ClaimConflict("cannot settle while a line item is under review")

    snapshot_dto, _ = load_snapshot_dtos(claim.snapshot)
    policy = claim.policy

    total_paid = ZERO
    deductible_absorbed = ZERO
    sub_limit_increments: dict[str, Decimal] = {}
    paid_count = 0

    for line in claim.line_items:
        # Deductible the member absorbed counts toward the annual deductible, whether or
        # not the line ends up payable.
        for reason in line.reasons:
            if reason.code is ReasonCode.DEDUCTIBLE:
                deductible_absorbed += -reason.amount_delta

        if line.status in (LineItemStatus.APPROVED, LineItemStatus.PARTIALLY_APPROVED):
            line.status = transition(line.status, LineItemStatus.PAID)
            total_paid += line.payable_amount
            paid_count += 1
            rule = snapshot_dto.coverage_types.get(line.coverage_type_code)
            # Only per-year sub-limits accumulate across claims (per_day/per_claim reset).
            if (
                rule is not None
                and rule.sub_limit_type is not SubLimitType.NONE
                and rule.sub_limit_basis is SubLimitBasis.PER_YEAR
            ):
                sub_limit_increments[rule.code] = (
                    sub_limit_increments.get(rule.code, ZERO) + line.payable_amount
                )

    policy.sum_insured_consumed = rupee(policy.sum_insured_consumed + total_paid)
    policy.deductible_consumed = rupee(policy.deductible_consumed + deductible_absorbed)
    if sub_limit_increments:
        # Reassign a new dict (JSON column, string values) so SQLAlchemy detects the change.
        consumed = dict(policy.sub_limit_consumed or {})
        for code, amount in sub_limit_increments.items():
            consumed[code] = str(rupee(Decimal(consumed.get(code, "0")) + amount))
        policy.sub_limit_consumed = consumed

    claim.stage = ClaimStage.SETTLED
    _log(
        session,
        claim,
        f"Claim settled: paid ₹{rupee(total_paid)} across {paid_count} line item(s); "
        "policy usage counters updated.",
    )
    session.flush()
    return claim


def raise_dispute(
    session,
    claim: orm.Claim,
    *,
    line_item_id: int | None,
    reason_text: str,
) -> orm.Dispute:
    """Member contests a decision (SPEC §5.4). A line-level dispute moves the line to
    `disputed` (remembering its prior decision) and re-opens the claim. Disputes are
    handled before settlement here — a paid line has no `disputed` edge (SPEC §3.4) and
    a settled claim is closed to disputes (documented simplification)."""
    if claim.stage in (ClaimStage.SETTLED, ClaimStage.CLOSED):
        raise ClaimConflict(f"claim {claim.id} is {claim.stage.value}; disputes are closed")

    line = None
    prior_status = None
    if line_item_id is not None:
        line = next((li for li in claim.line_items if li.id == line_item_id), None)
        if line is None:
            raise ClaimError(f"line item {line_item_id} is not on claim {claim.id}")
        if line.status not in (
            LineItemStatus.APPROVED,
            LineItemStatus.PARTIALLY_APPROVED,
            LineItemStatus.DENIED,
        ):
            raise ClaimConflict(
                f"line item {line_item_id} cannot be disputed from {line.status.value}"
            )
        prior_status = line.status
        line.status = transition(line.status, LineItemStatus.DISPUTED)

    dispute = orm.Dispute(
        claim_id=claim.id,
        line_item_id=line_item_id,
        reason_text=reason_text,
        state=DisputeState.RAISED,
        prior_status=prior_status,
    )
    session.add(dispute)
    # Re-open the claim while the dispute is pending (status left as last derived).
    claim.stage = ClaimStage.UNDER_ADJUDICATION
    target = f"line {line.ref}" if line else "claim"
    _log(session, claim, f"Dispute raised on {target}: {reason_text}", actor="member")
    session.flush()
    return dispute


def resolve_dispute(
    session,
    dispute: orm.Dispute,
    *,
    outcome: str,
    resolution_text: str,
    new_payable_amount: Decimal | None = None,
) -> orm.Dispute:
    """Resolve a dispute (SPEC §5.4). `upheld` restores the original decision;
    `overturned` moves the line to a covered decision (optionally at a corrected
    amount). The claim then re-derives from its line items."""
    if dispute.state in (DisputeState.UPHELD, DisputeState.OVERTURNED):
        raise ClaimConflict(f"dispute {dispute.id} is already resolved")

    claim = dispute.claim
    line = dispute.line_item

    if outcome == "upheld":
        if line is not None and dispute.prior_status is not None:
            line.status = transition(line.status, dispute.prior_status)
        dispute.state = DisputeState.UPHELD
        verb = "upheld; the original decision stands"
    elif outcome == "overturned":
        if line is None:
            raise ClaimError("an overturned dispute requires a line item")
        billed = line.billed_amount
        if new_payable_amount is not None:
            if not (ZERO < new_payable_amount <= billed):
                raise ClaimError("new_payable_amount must be 0 < x <= billed_amount")
            payable = rupee(new_payable_amount)
        else:
            payable = billed  # overturn to full approval when no amount is given
        new_status = (
            LineItemStatus.APPROVED if payable >= billed else LineItemStatus.PARTIALLY_APPROVED
        )
        line.status = transition(line.status, new_status)
        line.payable_amount = payable
        line.reasons.append(
            orm.Reason(
                ordinal=len(line.reasons),
                code=ReasonCode.DISPUTE_OVERTURNED,
                message=f"Dispute overturned; line set to ₹{payable}. {resolution_text}",
                amount_delta=ZERO,
                step=PipelineStep.NEEDS_REVIEW,
            )
        )
        dispute.state = DisputeState.OVERTURNED
        verb = f"overturned; line set to ₹{payable}"
    else:
        raise ClaimError(f"unknown outcome '{outcome}'")

    dispute.resolution_text = resolution_text
    dispute.resolved_at = datetime.now(timezone.utc)

    # Re-derive once the disputed line is back to a decided state. If other disputes are
    # still open, the claim stays under_adjudication until they resolve too.
    if any(li.status is LineItemStatus.DISPUTED for li in claim.line_items):
        claim.stage = ClaimStage.UNDER_ADJUDICATION
    else:
        claim.status, claim.stage = derive_claim_state([li.status for li in claim.line_items])
    _log(session, claim, f"Dispute {dispute.id} {verb}.", actor="adjuster")
    session.flush()
    return dispute


def readjudicate_claim(session, claim: orm.Claim) -> orm.Claim:
    """Re-run the engine against the claim's frozen snapshot and overwrite the stored
    results (SPEC §5.3). Deterministic: it reproduces the original automatic decision,
    discarding any manual review/dispute overrides — a clean reset for the demo. Not
    allowed once settled."""
    if claim.stage in (ClaimStage.SETTLED, ClaimStage.CLOSED):
        raise ClaimConflict(f"claim {claim.id} is {claim.stage.value}; cannot re-adjudicate")

    snapshot_dto, usage_dto = load_snapshot_dtos(claim.snapshot)
    inputs = [
        LineItemInput(
            ref=li.ref,
            coverage_type_code=li.coverage_type_code,
            billed_amount=li.billed_amount,
            service_days=li.service_days,
            diagnosis_code=li.diagnosis_code,
            provider_name=li.provider_name,
            description=li.description,
        )
        for li in claim.line_items
    ]
    result = adjudicate_claim(snapshot_dto, inputs, usage_dto, claim.service_date)
    results_by_ref = {r.ref: r for r in result.line_items}

    for line in claim.line_items:
        res = results_by_ref[line.ref]
        line.reasons.clear()  # delete-orphan cascade removes the old reason rows
        line.payable_amount = res.payable_amount
        line.status = res.status
        for ordinal, reason in enumerate(res.reasons):
            line.reasons.append(
                orm.Reason(
                    ordinal=ordinal,
                    code=reason.code,
                    message=reason.message,
                    amount_delta=reason.amount_delta,
                    step=reason.step,
                )
            )

    claim.status, claim.stage = result.status, result.stage
    _log(session, claim, "Claim re-adjudicated from the frozen snapshot.")
    session.flush()
    return claim


def _log(session, claim: orm.Claim, message: str, actor: str = "system") -> None:
    session.add(orm.DecisionLog(claim_id=claim.id, actor=actor, message=message))

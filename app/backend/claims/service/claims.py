"""Claim orchestration: submit → snapshot → adjudicate → persist → derive.

This service is the seam both the seed script and the FastAPI layer (milestone 3) call.
It wires the pure engine (milestone 1) to persistence (milestone 2): it never puts
business rules here — derivation and amounts come from the engine, this just persists
them and records the activity stream.
"""

from __future__ import annotations

from datetime import date

from ..domain.models import LineItemInput
from ..engine.pipeline import adjudicate_claim
from ..persistence import models as orm
from .snapshot import persist_snapshot


class ClaimError(ValueError):
    """Invalid claim submission (unknown policy/member, member not on policy, etc.)."""


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


def _log(session, claim: orm.Claim, message: str, actor: str = "system") -> None:
    session.add(orm.DecisionLog(claim_id=claim.id, actor=actor, message=message))

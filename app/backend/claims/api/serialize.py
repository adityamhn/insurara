"""Map ORM rows to API response schemas. Totals are computed from the persisted line
items so the wire response and the stored decision can never drift."""

from __future__ import annotations

from decimal import Decimal

from ..domain.money import rupee
from ..persistence import models as orm
from . import schemas


def _totals(claim: orm.Claim) -> schemas.TotalsOut:
    billed = sum((li.billed_amount for li in claim.line_items), Decimal("0"))
    payable = sum((li.payable_amount for li in claim.line_items), Decimal("0"))
    return schemas.TotalsOut(
        total_billed=rupee(billed),
        total_payable=rupee(payable),
        total_member_borne=rupee(billed - payable),
    )


def plan_out(plan: orm.CoveragePlan) -> schemas.PlanOut:
    return schemas.PlanOut(
        id=plan.id,
        name=plan.name,
        description=plan.description,
        sum_insured=plan.sum_insured,
        deductible=plan.deductible,
        copay_percent=plan.copay_percent,
        coverage_types=[
            schemas.CoverageTypeOut(
                code=ct.code,
                name=ct.name,
                covered=ct.covered,
                sub_limit_type=ct.sub_limit_type,
                sub_limit_value=ct.sub_limit_value,
                sub_limit_basis=ct.sub_limit_basis,
                waiting_period_days=ct.waiting_period_days,
                triggers_proportionate_deduction=ct.triggers_proportionate_deduction,
                subject_to_proportionate_deduction=ct.subject_to_proportionate_deduction,
            )
            for ct in plan.coverage_types
        ],
    )


def member_out(member: orm.Member) -> schemas.MemberOut:
    return schemas.MemberOut(id=member.id, name=member.name, dob=member.dob)


def policy_out(policy: orm.Policy) -> schemas.PolicyOut:
    plan = policy.plan
    consumed = {k: Decimal(v) for k, v in (policy.sub_limit_consumed or {}).items()}
    return schemas.PolicyOut(
        id=policy.id,
        policy_number=policy.policy_number,
        plan_id=plan.id,
        plan_name=plan.name,
        start_date=policy.start_date,
        end_date=policy.end_date,
        status=policy.status,
        members=[
            schemas.PolicyMemberOut(member_id=link.member_id, name=link.member.name, role=link.role)
            for link in policy.members
        ],
        usage=schemas.UsageOut(
            sum_insured=plan.sum_insured,
            sum_insured_consumed=policy.sum_insured_consumed,
            sum_insured_remaining=rupee(plan.sum_insured - policy.sum_insured_consumed),
            deductible=plan.deductible,
            deductible_consumed=policy.deductible_consumed,
            sub_limit_consumed=consumed,
        ),
    )


def _line_out(li: orm.LineItem) -> schemas.LineItemOut:
    return schemas.LineItemOut(
        id=li.id,
        ref=li.ref,
        coverage_type_code=li.coverage_type_code,
        billed_amount=li.billed_amount,
        payable_amount=li.payable_amount,
        member_share=rupee(li.billed_amount - li.payable_amount),
        status=li.status,
        diagnosis_code=li.diagnosis_code,
        provider_name=li.provider_name,
        description=li.description,
        reasons=[
            schemas.ReasonOut(
                code=r.code, message=r.message, amount_delta=r.amount_delta, step=r.step
            )
            for r in li.reasons
        ],
    )


def claim_summary_out(claim: orm.Claim) -> schemas.ClaimSummaryOut:
    return schemas.ClaimSummaryOut(
        id=claim.id,
        policy_id=claim.policy_id,
        policy_number=claim.policy.policy_number,
        member_id=claim.member_id,
        member_name=claim.member.name,
        service_date=claim.service_date,
        stage=claim.stage,
        status=claim.status,
        totals=_totals(claim),
    )


def dispute_out(dispute: orm.Dispute) -> schemas.DisputeOut:
    return schemas.DisputeOut(
        id=dispute.id,
        claim_id=dispute.claim_id,
        line_item_id=dispute.line_item_id,
        reason_text=dispute.reason_text,
        state=dispute.state,
        prior_status=dispute.prior_status,
        resolution_text=dispute.resolution_text,
        created_at=dispute.created_at,
        resolved_at=dispute.resolved_at,
    )


def claim_out(claim: orm.Claim) -> schemas.ClaimOut:
    return schemas.ClaimOut(
        **claim_summary_out(claim).model_dump(),
        policy_snapshot_id=claim.policy_snapshot_id,
        line_items=[_line_out(li) for li in claim.line_items],
        decision_logs=[
            schemas.DecisionLogOut(timestamp=log.timestamp, actor=log.actor, message=log.message)
            for log in claim.decision_logs
        ],
        disputes=[dispute_out(d) for d in claim.disputes],
    )


def explanation_out(claim: orm.Claim) -> schemas.ExplanationOut:
    """The member-facing EOB: each line's billed → ordered deduction steps → payable."""
    lines = [
        schemas.ExplanationLine(
            coverage_type_code=li.coverage_type_code,
            description=li.description,
            billed_amount=li.billed_amount,
            steps=[
                schemas.ExplanationStep(code=r.code, message=r.message, amount_delta=r.amount_delta)
                for r in li.reasons
            ],
            payable_amount=li.payable_amount,
            status=li.status,
        )
        for li in claim.line_items
    ]
    return schemas.ExplanationOut(
        claim_id=claim.id,
        status=claim.status,
        stage=claim.stage,
        lines=lines,
        totals=_totals(claim),
    )

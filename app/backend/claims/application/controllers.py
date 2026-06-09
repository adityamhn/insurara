"""Shared application controllers for every external adapter.

FastAPI routes and the reviewer MCP server both call these functions. That keeps
claim behavior in one place: controllers translate typed inputs into service calls
and serializers, while domain rules stay in the engine/service layer.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..api import schemas, serialize
from ..api.errors import NotFound
from ..domain.enums import ClaimStage, ClaimStatus
from ..domain.models import LineItemInput
from ..persistence import models as orm
from ..seed import seed
from ..service.claims import (
    create_claim,
    raise_dispute,
    readjudicate_claim,
    resolve_dispute,
    resolve_review,
    settle_claim,
)


def _get_claim_row(session: Session, claim_id: int) -> orm.Claim:
    claim = session.get(orm.Claim, claim_id)
    if claim is None:
        raise NotFound(f"claim {claim_id} not found")
    return claim


def _get_dispute_row(session: Session, dispute_id: int) -> orm.Dispute:
    dispute = session.get(orm.Dispute, dispute_id)
    if dispute is None:
        raise NotFound(f"dispute {dispute_id} not found")
    return dispute


def list_plans(session: Session) -> list[schemas.PlanOut]:
    plans = session.scalars(select(orm.CoveragePlan)).all()
    return [serialize.plan_out(p) for p in plans]


def get_plan(session: Session, plan_id: int) -> schemas.PlanOut:
    plan = session.get(orm.CoveragePlan, plan_id)
    if plan is None:
        raise NotFound(f"plan {plan_id} not found")
    return serialize.plan_out(plan)


def list_policies(session: Session) -> list[schemas.PolicyOut]:
    policies = session.scalars(select(orm.Policy)).all()
    return [serialize.policy_out(p) for p in policies]


def get_policy(session: Session, policy_id: int) -> schemas.PolicyOut:
    policy = session.get(orm.Policy, policy_id)
    if policy is None:
        raise NotFound(f"policy {policy_id} not found")
    return serialize.policy_out(policy)


def list_members(session: Session) -> list[schemas.MemberOut]:
    members = session.scalars(select(orm.Member)).all()
    return [serialize.member_out(m) for m in members]


def submit_claim(session: Session, body: schemas.ClaimCreate) -> schemas.ClaimOut:
    line_items = [
        LineItemInput(
            ref="",
            coverage_type_code=li.coverage_type_code,
            billed_amount=li.billed_amount,
            service_days=li.service_days,
            diagnosis_code=li.diagnosis_code,
            provider_name=li.provider_name,
            description=li.description,
        )
        for li in body.line_items
    ]
    claim = create_claim(
        session,
        policy_id=body.policy_id,
        member_id=body.member_id,
        service_date=body.service_date,
        line_items=line_items,
    )
    return serialize.claim_out(claim)


def list_claims(
    session: Session,
    *,
    status: ClaimStatus | None = None,
    stage: ClaimStage | None = None,
    policy_id: int | None = None,
) -> list[schemas.ClaimSummaryOut]:
    stmt = select(orm.Claim).order_by(orm.Claim.id)
    if status is not None:
        stmt = stmt.where(orm.Claim.status == status)
    if stage is not None:
        stmt = stmt.where(orm.Claim.stage == stage)
    if policy_id is not None:
        stmt = stmt.where(orm.Claim.policy_id == policy_id)
    return [serialize.claim_summary_out(c) for c in session.scalars(stmt).all()]


def get_claim(session: Session, claim_id: int) -> schemas.ClaimOut:
    return serialize.claim_out(_get_claim_row(session, claim_id))


def get_explanation(session: Session, claim_id: int) -> schemas.ExplanationOut:
    return serialize.explanation_out(_get_claim_row(session, claim_id))


def resolve_line_review(
    session: Session,
    claim_id: int,
    line_item_id: int,
    body: schemas.ResolveReviewRequest,
) -> schemas.ClaimOut:
    claim = resolve_review(
        session,
        _get_claim_row(session, claim_id),
        line_item_id=line_item_id,
        decision=body.decision,
        payable_amount=body.payable_amount,
        note=body.note,
    )
    return serialize.claim_out(claim)


def settle(session: Session, claim_id: int) -> schemas.ClaimOut:
    return serialize.claim_out(settle_claim(session, _get_claim_row(session, claim_id)))


def readjudicate(session: Session, claim_id: int) -> schemas.ClaimOut:
    return serialize.claim_out(readjudicate_claim(session, _get_claim_row(session, claim_id)))


def create_dispute(
    session: Session,
    claim_id: int,
    body: schemas.DisputeCreate,
) -> schemas.DisputeOut:
    dispute = raise_dispute(
        session,
        _get_claim_row(session, claim_id),
        line_item_id=body.line_item_id,
        reason_text=body.reason_text,
    )
    return serialize.dispute_out(dispute)


def list_disputes(session: Session, claim_id: int) -> list[schemas.DisputeOut]:
    claim = _get_claim_row(session, claim_id)
    return [serialize.dispute_out(d) for d in claim.disputes]


def resolve_dispute_by_id(
    session: Session,
    dispute_id: int,
    body: schemas.DisputeResolve,
) -> schemas.DisputeOut:
    resolved = resolve_dispute(
        session,
        _get_dispute_row(session, dispute_id),
        outcome=body.outcome,
        resolution_text=body.resolution_text,
        new_payable_amount=body.new_payable_amount,
    )
    return serialize.dispute_out(resolved)


def reset_demo_data(session: Session) -> list[schemas.ClaimSummaryOut]:
    """Reset the current database to the SPEC §9 demo story.

    This is intentionally available only to reviewer/demo adapters. It uses the
    same seed function as tests and the README command, not a second data setup.
    """
    bind = session.get_bind()
    orm.Base.metadata.drop_all(bind)
    orm.Base.metadata.create_all(bind)
    seed(session)
    session.flush()
    return list_claims(session)


def worked_example_claim(session: Session) -> schemas.ClaimOut:
    claim = next(
        (
            c
            for c in list_claims(session)
            if c.totals.total_billed == Decimal("64000.00")
            and c.totals.total_payable == Decimal("41400.00")
        ),
        None,
    )
    if claim is None:
        raise NotFound("worked-example claim not found; run reset_demo_data first")
    return get_claim(session, claim.id)

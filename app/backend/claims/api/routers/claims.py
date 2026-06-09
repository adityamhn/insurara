"""Claims: submit (adjudicate on submit), list, detail, and the EOB explanation (SPEC §5.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.enums import ClaimStage, ClaimStatus
from ...domain.models import LineItemInput
from ...persistence import models as orm
from ...service.claims import create_claim
from .. import schemas, serialize
from ..deps import get_session
from ..errors import NotFound

router = APIRouter(prefix="/api/claims", tags=["claims"])


def _get_claim(session: Session, claim_id: int) -> orm.Claim:
    claim = session.get(orm.Claim, claim_id)
    if claim is None:
        raise NotFound(f"claim {claim_id} not found")
    return claim


@router.post("", response_model=schemas.ClaimOut, status_code=201)
def submit_claim(body: schemas.ClaimCreate, session: Session = Depends(get_session)):
    line_items = [
        LineItemInput(
            ref="",  # create_claim assigns a stable ref
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


@router.get("", response_model=list[schemas.ClaimSummaryOut])
def list_claims(
    session: Session = Depends(get_session),
    status: ClaimStatus | None = Query(default=None),
    stage: ClaimStage | None = Query(default=None),
    policy_id: int | None = Query(default=None),
):
    stmt = select(orm.Claim).order_by(orm.Claim.id)
    if status is not None:
        stmt = stmt.where(orm.Claim.status == status)
    if stage is not None:
        stmt = stmt.where(orm.Claim.stage == stage)
    if policy_id is not None:
        stmt = stmt.where(orm.Claim.policy_id == policy_id)
    return [serialize.claim_summary_out(c) for c in session.scalars(stmt).all()]


@router.get("/{claim_id}", response_model=schemas.ClaimOut)
def get_claim(claim_id: int, session: Session = Depends(get_session)):
    return serialize.claim_out(_get_claim(session, claim_id))


@router.get("/{claim_id}/explanation", response_model=schemas.ExplanationOut)
def get_explanation(claim_id: int, session: Session = Depends(get_session)):
    return serialize.explanation_out(_get_claim(session, claim_id))

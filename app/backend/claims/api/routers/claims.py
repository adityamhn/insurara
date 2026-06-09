"""Claims: submit (adjudicate on submit), list, detail, and the EOB explanation (SPEC §5.2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...application import controllers
from ...domain.enums import ClaimStage, ClaimStatus
from .. import schemas
from ..deps import get_session

router = APIRouter(prefix="/api/claims", tags=["claims"])


@router.post("", response_model=schemas.ClaimOut, status_code=201)
def submit_claim(body: schemas.ClaimCreate, session: Session = Depends(get_session)):
    return controllers.submit_claim(session, body)


@router.get("", response_model=list[schemas.ClaimSummaryOut])
def list_claims(
    session: Session = Depends(get_session),
    status: ClaimStatus | None = Query(default=None),
    stage: ClaimStage | None = Query(default=None),
    policy_id: int | None = Query(default=None),
):
    return controllers.list_claims(session, status=status, stage=stage, policy_id=policy_id)


@router.get("/{claim_id}", response_model=schemas.ClaimOut)
def get_claim(claim_id: int, session: Session = Depends(get_session)):
    return controllers.get_claim(session, claim_id)


@router.get("/{claim_id}/explanation", response_model=schemas.ExplanationOut)
def get_explanation(claim_id: int, session: Session = Depends(get_session)):
    return controllers.get_explanation(session, claim_id)


@router.post(
    "/{claim_id}/line-items/{line_item_id}/resolve-review",
    response_model=schemas.ClaimOut,
)
def resolve_line_review(
    claim_id: int,
    line_item_id: int,
    body: schemas.ResolveReviewRequest,
    session: Session = Depends(get_session),
):
    return controllers.resolve_line_review(session, claim_id, line_item_id, body)


@router.post("/{claim_id}/settle", response_model=schemas.ClaimOut)
def settle(claim_id: int, session: Session = Depends(get_session)):
    return controllers.settle(session, claim_id)


@router.post("/{claim_id}/readjudicate", response_model=schemas.ClaimOut)
def readjudicate(claim_id: int, session: Session = Depends(get_session)):
    return controllers.readjudicate(session, claim_id)


@router.post("/{claim_id}/disputes", response_model=schemas.DisputeOut, status_code=201)
def create_dispute(
    claim_id: int,
    body: schemas.DisputeCreate,
    session: Session = Depends(get_session),
):
    return controllers.create_dispute(session, claim_id, body)


@router.get("/{claim_id}/disputes", response_model=list[schemas.DisputeOut])
def list_disputes(claim_id: int, session: Session = Depends(get_session)):
    return controllers.list_disputes(session, claim_id)

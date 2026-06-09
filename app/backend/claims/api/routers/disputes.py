"""Dispute resolution (SPEC §5.4). Resolving lives under /api/disputes because it acts
on a dispute id, not a claim; raising/listing disputes is on the claims router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application import controllers
from .. import schemas
from ..deps import get_session

router = APIRouter(prefix="/api/disputes", tags=["disputes"])


@router.post("/{dispute_id}/resolve", response_model=schemas.DisputeOut)
def resolve(
    dispute_id: int,
    body: schemas.DisputeResolve,
    session: Session = Depends(get_session),
):
    return controllers.resolve_dispute_by_id(session, dispute_id, body)

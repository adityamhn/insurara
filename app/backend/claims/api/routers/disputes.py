"""Dispute resolution (SPEC §5.4). Resolving lives under /api/disputes because it acts
on a dispute id, not a claim; raising/listing disputes is on the claims router."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...persistence import models as orm
from ...service.claims import resolve_dispute
from .. import schemas, serialize
from ..deps import get_session
from ..errors import NotFound

router = APIRouter(prefix="/api/disputes", tags=["disputes"])


@router.post("/{dispute_id}/resolve", response_model=schemas.DisputeOut)
def resolve(
    dispute_id: int,
    body: schemas.DisputeResolve,
    session: Session = Depends(get_session),
):
    dispute = session.get(orm.Dispute, dispute_id)
    if dispute is None:
        raise NotFound(f"dispute {dispute_id} not found")
    resolved = resolve_dispute(
        session,
        dispute,
        outcome=body.outcome,
        resolution_text=body.resolution_text,
        new_payable_amount=body.new_payable_amount,
    )
    return serialize.dispute_out(resolved)

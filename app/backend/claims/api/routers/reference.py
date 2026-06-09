"""Read-only reference data: plans, policies (with usage), members."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ...application import controllers
from .. import schemas
from ..deps import get_session

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/plans", response_model=list[schemas.PlanOut])
def list_plans(session: Session = Depends(get_session)):
    return controllers.list_plans(session)


@router.get("/plans/{plan_id}", response_model=schemas.PlanOut)
def get_plan(plan_id: int, session: Session = Depends(get_session)):
    return controllers.get_plan(session, plan_id)


@router.get("/policies", response_model=list[schemas.PolicyOut])
def list_policies(session: Session = Depends(get_session)):
    return controllers.list_policies(session)


@router.get("/policies/{policy_id}", response_model=schemas.PolicyOut)
def get_policy(policy_id: int, session: Session = Depends(get_session)):
    return controllers.get_policy(session, policy_id)


@router.get("/members", response_model=list[schemas.MemberOut])
def list_members(session: Session = Depends(get_session)):
    return controllers.list_members(session)

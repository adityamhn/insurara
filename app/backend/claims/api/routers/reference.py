"""Read-only reference data: plans, policies (with usage), members (SPEC §5.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...persistence import models as orm
from .. import schemas, serialize
from ..deps import get_session
from ..errors import NotFound

router = APIRouter(prefix="/api", tags=["reference"])


@router.get("/plans", response_model=list[schemas.PlanOut])
def list_plans(session: Session = Depends(get_session)):
    plans = session.scalars(select(orm.CoveragePlan)).all()
    return [serialize.plan_out(p) for p in plans]


@router.get("/plans/{plan_id}", response_model=schemas.PlanOut)
def get_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(orm.CoveragePlan, plan_id)
    if plan is None:
        raise NotFound(f"plan {plan_id} not found")
    return serialize.plan_out(plan)


@router.get("/policies", response_model=list[schemas.PolicyOut])
def list_policies(session: Session = Depends(get_session)):
    policies = session.scalars(select(orm.Policy)).all()
    return [serialize.policy_out(p) for p in policies]


@router.get("/policies/{policy_id}", response_model=schemas.PolicyOut)
def get_policy(policy_id: int, session: Session = Depends(get_session)):
    policy = session.get(orm.Policy, policy_id)
    if policy is None:
        raise NotFound(f"policy {policy_id} not found")
    return serialize.policy_out(policy)


@router.get("/members", response_model=list[schemas.MemberOut])
def list_members(session: Session = Depends(get_session)):
    members = session.scalars(select(orm.Member)).all()
    return [serialize.member_out(m) for m in members]

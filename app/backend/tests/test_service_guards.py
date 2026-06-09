"""Claim-submission guards (Decision: a claim can't be filed against a policy that
isn't in force or for a service date outside the policy period)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from claims.domain.models import LineItemInput
from claims.persistence import models as orm
from claims.service.claims import ClaimError, create_claim


def _policy(session, number: str) -> orm.Policy:
    return session.scalars(select(orm.Policy).where(orm.Policy.policy_number == number)).one()


def _line(code: str, billed: str) -> LineItemInput:
    return LineItemInput(ref=code, coverage_type_code=code, billed_amount=Decimal(billed))


def test_lapsed_policy_rejects_claims(seeded):
    session, _ = seeded
    policy = _policy(session, "AS3L-CLEAN-0003")
    policy.status = "lapsed"
    session.flush()
    with pytest.raises(ClaimError, match="lapsed"):
        create_claim(
            session,
            policy_id=policy.id,
            member_id=policy.members[0].member_id,
            service_date=date(2024, 6, 1),
            line_items=[_line("daycare", "1000")],
        )


def test_service_date_outside_policy_period_rejected(seeded):
    session, _ = seeded
    policy = _policy(session, "AS3L-EXHAUST-0002")  # ends 2024-05-31
    with pytest.raises(ClaimError, match="outside the policy period"):
        create_claim(
            session,
            policy_id=policy.id,
            member_id=policy.members[0].member_id,
            service_date=date(2024, 8, 1),
            line_items=[_line("surgery", "1000")],
        )

"""Freeze a live policy into the immutable terms the engine adjudicates against
(Decision 7). Built at claim creation; later edits to the policy/plan never reach a
past claim because adjudication only ever reads the snapshot.
"""

from __future__ import annotations

from decimal import Decimal

from ..domain.models import CoverageTypeRule, PolicySnapshot, UsageCounters
from ..persistence import models as orm


def build_snapshot_dto(policy: orm.Policy) -> PolicySnapshot:
    """Project the live policy + its plan's coverage types into a frozen DTO."""
    plan = policy.plan
    rules = {
        ct.code: CoverageTypeRule(
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
    }
    return PolicySnapshot(
        policy_number=policy.policy_number,
        start_date=policy.start_date,
        sum_insured=plan.sum_insured,
        deductible=plan.deductible,
        copay_percent=plan.copay_percent,
        coverage_types=rules,
        high_value_review_threshold=plan.high_value_review_threshold,
    )


def build_usage_dto(policy: orm.Policy) -> UsageCounters:
    """Capture the live usage counters as they stand at snapshot time."""
    return UsageCounters(
        sum_insured_consumed=policy.sum_insured_consumed,
        deductible_consumed=policy.deductible_consumed,
        sub_limit_consumed={
            code: Decimal(amount) for code, amount in (policy.sub_limit_consumed or {}).items()
        },
    )


def persist_snapshot(
    session, policy: orm.Policy
) -> tuple[orm.PolicySnapshot, PolicySnapshot, UsageCounters]:
    """Build the frozen DTOs, store them as exact pydantic JSON, and return both the
    ORM row and the DTOs (so the caller can adjudicate without re-reading)."""
    snapshot_dto = build_snapshot_dto(policy)
    usage_dto = build_usage_dto(policy)
    row = orm.PolicySnapshot(
        policy_id=policy.id,
        snapshot_json=snapshot_dto.model_dump_json(),
        usage_json=usage_dto.model_dump_json(),
    )
    session.add(row)
    session.flush()  # assign row.id for the claim FK
    return row, snapshot_dto, usage_dto


def load_snapshot_dtos(row: orm.PolicySnapshot) -> tuple[PolicySnapshot, UsageCounters]:
    """Reconstruct the frozen DTOs from a stored snapshot row (for re-adjudication)."""
    return (
        PolicySnapshot.model_validate_json(row.snapshot_json),
        UsageCounters.model_validate_json(row.usage_json),
    )

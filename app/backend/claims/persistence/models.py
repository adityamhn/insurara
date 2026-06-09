"""ORM models — the tables of SPEC §6.2.

The engine never sees these (it works on the pure DTOs in `domain.models`); the service
layer maps between them. Money columns use the `Money` TEXT type for exact Decimals.
Status columns store the domain enums as validated strings (no native DB enum, so the
schema stays portable across SQLite/Postgres).

SENSITIVE fields (Decision 10) are tagged in comments: in production these would be
column-encrypted and gated behind a reader-role ACL. We document the intent, not enforce
it (auth/encryption are out of scope).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..domain.enums import (
    ClaimStage,
    ClaimStatus,
    DisputeState,
    LineItemStatus,
    PipelineStep,
    ReasonCode,
    SubLimitBasis,
    SubLimitType,
)
from .db import Base
from .types import Money


def _enum(enum_cls) -> SAEnum:
    """Store a Python enum as a validated VARCHAR (portable; no native DB enum)."""
    return SAEnum(enum_cls, native_enum=False, validate_strings=True, length=32)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CoveragePlan(Base):
    __tablename__ = "coverage_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    sum_insured: Mapped[Money] = mapped_column(Money)
    deductible: Mapped[Money] = mapped_column(Money, default=Decimal("0"))
    copay_percent: Mapped[Money] = mapped_column(Money, default=Decimal("0"))
    # Auto-vs-human split (Decision 9): line items billed above this route to review.
    high_value_review_threshold: Mapped[Money] = mapped_column(Money, default=Decimal("100000"))

    coverage_types: Mapped[list[CoverageType]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
    policies: Mapped[list[Policy]] = relationship(back_populates="plan")


class CoverageType(Base):
    """One coverage category and its rules — the decision-table row (Decision 2)."""

    __tablename__ = "coverage_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("coverage_plans.id"))
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    covered: Mapped[bool] = mapped_column(Boolean, default=True)
    sub_limit_type: Mapped[SubLimitType] = mapped_column(
        _enum(SubLimitType), default=SubLimitType.NONE
    )
    sub_limit_value: Mapped[Money | None] = mapped_column(Money, default=None)
    sub_limit_basis: Mapped[SubLimitBasis] = mapped_column(
        _enum(SubLimitBasis), default=SubLimitBasis.PER_CLAIM
    )
    waiting_period_days: Mapped[int] = mapped_column(Integer, default=0)
    triggers_proportionate_deduction: Mapped[bool] = mapped_column(Boolean, default=False)
    subject_to_proportionate_deduction: Mapped[bool] = mapped_column(Boolean, default=False)

    plan: Mapped[CoveragePlan] = relationship(back_populates="coverage_types")


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))  # SENSITIVE: encrypt + reader-role ACL
    dob: Mapped[date] = mapped_column()

    policy_links: Mapped[list[PolicyMember]] = relationship(back_populates="member")


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_number: Mapped[str] = mapped_column(String(40), unique=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("coverage_plans.id"))
    start_date: Mapped[date] = mapped_column()
    end_date: Mapped[date] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), default="in_force")

    # Live usage counters (SPEC §3.3), incremented on settlement (milestone 4).
    sum_insured_consumed: Mapped[Money] = mapped_column(Money, default=Decimal("0"))
    deductible_consumed: Mapped[Money] = mapped_column(Money, default=Decimal("0"))
    # Per-coverage-type consumed, keyed by code; Decimal values stored as strings.
    sub_limit_consumed: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)

    plan: Mapped[CoveragePlan] = relationship(back_populates="policies")
    members: Mapped[list[PolicyMember]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )
    claims: Mapped[list[Claim]] = relationship(back_populates="policy")


class PolicyMember(Base):
    """Member ↔ Policy with a role; multiple rows = family floater (Decision 11)."""

    __tablename__ = "policy_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    role: Mapped[str] = mapped_column(String(20), default="primary")  # primary | dependent

    policy: Mapped[Policy] = relationship(back_populates="members")
    member: Mapped[Member] = relationship(back_populates="policy_links")


class PolicySnapshot(Base):
    """Frozen policy terms + usage counters at claim creation (Decision 7). Stored as
    pydantic JSON text so it round-trips Decimals exactly and is immune to later policy
    edits. The claim FK-references this; the engine reads from here, never the live plan."""

    __tablename__ = "policy_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    snapshot_json: Mapped[str] = mapped_column(Text)  # PolicySnapshot DTO
    usage_json: Mapped[str] = mapped_column(Text)  # UsageCounters DTO


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey("policies.id"))
    policy_snapshot_id: Mapped[int] = mapped_column(ForeignKey("policy_snapshots.id"))
    member_id: Mapped[int] = mapped_column(ForeignKey("members.id"))
    service_date: Mapped[date] = mapped_column()
    stage: Mapped[ClaimStage] = mapped_column(_enum(ClaimStage), default=ClaimStage.SUBMITTED)
    status: Mapped[ClaimStatus | None] = mapped_column(_enum(ClaimStatus), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    policy: Mapped[Policy] = relationship(back_populates="claims")
    snapshot: Mapped[PolicySnapshot] = relationship()
    member: Mapped[Member] = relationship()
    line_items: Mapped[list[LineItem]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="LineItem.id"
    )
    decision_logs: Mapped[list[DecisionLog]] = relationship(
        back_populates="claim", cascade="all, delete-orphan", order_by="DecisionLog.id"
    )
    disputes: Mapped[list[Dispute]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))
    ref: Mapped[str] = mapped_column(String(40))  # ties back to the engine result
    coverage_type_code: Mapped[str] = mapped_column(String(40))
    billed_amount: Mapped[Money] = mapped_column(Money)
    payable_amount: Mapped[Money] = mapped_column(Money, default=Decimal("0"))
    service_days: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[LineItemStatus] = mapped_column(
        _enum(LineItemStatus), default=LineItemStatus.SUBMITTED
    )
    diagnosis_code: Mapped[str | None] = mapped_column(
        String(40), default=None
    )  # SENSITIVE: encrypt + reader-role ACL
    provider_name: Mapped[str | None] = mapped_column(
        String(160), default=None
    )  # SENSITIVE: encrypt + reader-role ACL
    description: Mapped[str | None] = mapped_column(Text, default=None)

    claim: Mapped[Claim] = relationship(back_populates="line_items")
    reasons: Mapped[list[Reason]] = relationship(
        back_populates="line_item", cascade="all, delete-orphan", order_by="Reason.ordinal"
    )


class Reason(Base):
    """A structured explanation fragment (Decision 6); ordered to render the waterfall."""

    __tablename__ = "reasons"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_item_id: Mapped[int | None] = mapped_column(ForeignKey("line_items.id"), default=None)
    claim_id: Mapped[int | None] = mapped_column(ForeignKey("claims.id"), default=None)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)  # pipeline order
    code: Mapped[ReasonCode] = mapped_column(_enum(ReasonCode))
    message: Mapped[str] = mapped_column(Text)
    amount_delta: Mapped[Money] = mapped_column(Money, default=Decimal("0"))
    step: Mapped[PipelineStep] = mapped_column(_enum(PipelineStep))

    line_item: Mapped[LineItem | None] = relationship(back_populates="reasons")


class DecisionLog(Base):
    """Append-only claim-level activity stream (Decision 6)."""

    __tablename__ = "decision_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=_now)
    actor: Mapped[str] = mapped_column(String(40), default="system")
    message: Mapped[str] = mapped_column(Text)

    claim: Mapped[Claim] = relationship(back_populates="decision_logs")


class Dispute(Base):
    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"))
    line_item_id: Mapped[int | None] = mapped_column(ForeignKey("line_items.id"), default=None)
    reason_text: Mapped[str] = mapped_column(Text)
    state: Mapped[DisputeState] = mapped_column(_enum(DisputeState), default=DisputeState.RAISED)
    resolution_text: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    claim: Mapped[Claim] = relationship(back_populates="disputes")

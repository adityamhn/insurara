"""Pydantic request/response schemas for the REST API.

Kept separate from the domain DTOs and the ORM so the wire contract can evolve
independently. Money is serialized as exact 2dp decimal strings (pydantic renders
Decimal as a string) — one consistent money representation across the API.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from ..domain.enums import (
    ClaimStage,
    ClaimStatus,
    DisputeState,
    LineItemStatus,
    PipelineStep,
    PolicyStatus,
    ReasonCode,
    SubLimitBasis,
    SubLimitType,
)

# --- Reference data ---------------------------------------------------------- #


class CoverageTypeOut(BaseModel):
    code: str
    name: str
    covered: bool
    sub_limit_type: SubLimitType
    sub_limit_value: Decimal | None
    sub_limit_basis: SubLimitBasis
    waiting_period_days: int
    triggers_proportionate_deduction: bool
    subject_to_proportionate_deduction: bool


class PlanOut(BaseModel):
    id: int
    name: str
    description: str | None
    sum_insured: Decimal
    deductible: Decimal
    copay_percent: Decimal
    coverage_types: list[CoverageTypeOut]


class MemberOut(BaseModel):
    id: int
    name: str  # SENSITIVE — surfaced for the demo, flagged in meta
    dob: date


class PolicyMemberOut(BaseModel):
    member_id: int
    name: str
    role: str


class UsageOut(BaseModel):
    sum_insured: Decimal
    sum_insured_consumed: Decimal
    sum_insured_remaining: Decimal
    deductible: Decimal
    deductible_consumed: Decimal
    sub_limit_consumed: dict[str, Decimal]


class PolicyOut(BaseModel):
    id: int
    policy_number: str
    plan_id: int
    plan_name: str
    start_date: date
    end_date: date
    status: PolicyStatus
    members: list[PolicyMemberOut]
    usage: UsageOut


# --- Claims ------------------------------------------------------------------ #


class LineItemCreate(BaseModel):
    coverage_type_code: str
    billed_amount: Decimal = Field(gt=0)
    service_days: int = Field(default=1, ge=1)
    diagnosis_code: str | None = None
    provider_name: str | None = None
    description: str | None = None


class ClaimCreate(BaseModel):
    policy_id: int
    member_id: int
    service_date: date
    line_items: list[LineItemCreate] = Field(min_length=1)


class ResolveReviewRequest(BaseModel):
    decision: Literal["approve", "partially_approve", "deny"]
    payable_amount: Decimal | None = Field(default=None, gt=0)
    note: str | None = None


class ReasonOut(BaseModel):
    code: ReasonCode
    message: str
    amount_delta: Decimal
    step: PipelineStep


class LineItemOut(BaseModel):
    id: int
    ref: str
    coverage_type_code: str
    billed_amount: Decimal
    payable_amount: Decimal
    member_share: Decimal
    status: LineItemStatus
    diagnosis_code: str | None
    provider_name: str | None
    description: str | None
    reasons: list[ReasonOut]


class TotalsOut(BaseModel):
    total_billed: Decimal
    total_payable: Decimal
    total_member_borne: Decimal


class DecisionLogOut(BaseModel):
    timestamp: datetime
    actor: str
    message: str


class DisputeCreate(BaseModel):
    line_item_id: int | None = None
    reason_text: str = Field(min_length=1)


class DisputeResolve(BaseModel):
    outcome: Literal["upheld", "overturned"]
    resolution_text: str = Field(min_length=1)
    new_payable_amount: Decimal | None = Field(default=None, gt=0)


class DisputeOut(BaseModel):
    id: int
    claim_id: int
    line_item_id: int | None
    reason_text: str
    state: DisputeState
    prior_status: LineItemStatus | None
    resolution_text: str | None
    created_at: datetime
    resolved_at: datetime | None


class ClaimSummaryOut(BaseModel):
    id: int
    policy_id: int
    policy_number: str
    member_id: int
    member_name: str
    service_date: date
    stage: ClaimStage
    status: ClaimStatus | None
    totals: TotalsOut


class ClaimOut(ClaimSummaryOut):
    policy_snapshot_id: int
    line_items: list[LineItemOut]
    decision_logs: list[DecisionLogOut]
    disputes: list[DisputeOut]


# --- Explanation (EOB) ------------------------------------------------------- #


class ExplanationStep(BaseModel):
    code: ReasonCode
    message: str
    amount_delta: Decimal


class ExplanationLine(BaseModel):
    coverage_type_code: str
    description: str | None
    billed_amount: Decimal
    steps: list[ExplanationStep]
    payable_amount: Decimal
    status: LineItemStatus


class ExplanationOut(BaseModel):
    claim_id: int
    status: ClaimStatus | None
    stage: ClaimStage
    lines: list[ExplanationLine]
    totals: TotalsOut


# --- Errors ------------------------------------------------------------------ #


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorOut(BaseModel):
    error: ErrorBody

// TypeScript mirror of the FastAPI response schemas (app/backend/claims/api/schemas.py).
// Money and percent fields arrive as exact 2dp decimal STRINGS — never parse to float
// for anything but display.

export type ClaimStatus = "approved" | "partially_approved" | "denied" | "needs_review";
export type ClaimStage =
  | "submitted"
  | "under_adjudication"
  | "decided"
  | "settled"
  | "closed";
export type LineItemStatus =
  | "submitted"
  | "under_review"
  | "approved"
  | "partially_approved"
  | "denied"
  | "paid"
  | "disputed";
export type DisputeState = "raised" | "under_review" | "upheld" | "overturned";

export interface CoverageType {
  code: string;
  name: string;
  covered: boolean;
  sub_limit_type: "none" | "absolute" | "percent_of_si";
  sub_limit_value: string | null;
  sub_limit_basis: "per_day" | "per_claim" | "per_year";
  waiting_period_days: number;
  triggers_proportionate_deduction: boolean;
  subject_to_proportionate_deduction: boolean;
}

export interface Plan {
  id: number;
  name: string;
  description: string | null;
  sum_insured: string;
  deductible: string;
  copay_percent: string;
  coverage_types: CoverageType[];
}

export interface Member {
  id: number;
  name: string;
  dob: string;
}

export interface PolicyMember {
  member_id: number;
  name: string;
  role: string;
}

export interface Usage {
  sum_insured: string;
  sum_insured_consumed: string;
  sum_insured_remaining: string;
  deductible: string;
  deductible_consumed: string;
  sub_limit_consumed: Record<string, string>;
}

export interface Policy {
  id: number;
  policy_number: string;
  plan_id: number;
  plan_name: string;
  start_date: string;
  end_date: string;
  status: string;
  members: PolicyMember[];
  usage: Usage;
}

export interface Reason {
  code: string;
  message: string;
  amount_delta: string;
  step: string;
}

export interface LineItem {
  id: number;
  ref: string;
  coverage_type_code: string;
  billed_amount: string;
  payable_amount: string;
  member_share: string;
  status: LineItemStatus;
  diagnosis_code: string | null;
  provider_name: string | null;
  description: string | null;
  reasons: Reason[];
}

export interface Totals {
  total_billed: string;
  total_payable: string;
  total_member_borne: string;
}

export interface DecisionLog {
  timestamp: string;
  actor: string;
  message: string;
}

export interface Dispute {
  id: number;
  claim_id: number;
  line_item_id: number | null;
  reason_text: string;
  state: DisputeState;
  prior_status: LineItemStatus | null;
  resolution_text: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface ClaimSummary {
  id: number;
  policy_id: number;
  policy_number: string;
  member_id: number;
  member_name: string;
  service_date: string;
  stage: ClaimStage;
  status: ClaimStatus | null;
  totals: Totals;
}

export interface Claim extends ClaimSummary {
  policy_snapshot_id: number;
  line_items: LineItem[];
  decision_logs: DecisionLog[];
  disputes: Dispute[];
}

export interface ExplanationStep {
  code: string;
  message: string;
  amount_delta: string;
}

export interface ExplanationLine {
  coverage_type_code: string;
  description: string | null;
  billed_amount: string;
  steps: ExplanationStep[];
  payable_amount: string;
  status: LineItemStatus;
}

export interface Explanation {
  claim_id: number;
  status: ClaimStatus | null;
  stage: ClaimStage;
  lines: ExplanationLine[];
  totals: Totals;
}

// Request bodies
export interface LineItemCreate {
  coverage_type_code: string;
  billed_amount: string;
  service_days?: number;
  diagnosis_code?: string | null;
  provider_name?: string | null;
  description?: string | null;
}

export interface ClaimCreate {
  policy_id: number;
  member_id: number;
  service_date: string;
  line_items: LineItemCreate[];
}

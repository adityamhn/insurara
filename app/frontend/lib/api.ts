// Typed client for the FastAPI backend. Works from both Server Components (server-side
// fetch, no-store) and Client Components (browser → backend; CORS allows :3000).

import type {
  Claim,
  ClaimCreate,
  ClaimSummary,
  ClaimStatus,
  Dispute,
  Explanation,
  Member,
  Plan,
  Policy,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${BASE}${path}`, { cache: "no-store" }));
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

// Reference data
export const listPlans = () => get<Plan[]>("/api/plans");
export const getPlan = (id: number) => get<Plan>(`/api/plans/${id}`);
export const listPolicies = () => get<Policy[]>("/api/policies");
export const getPolicy = (id: number) => get<Policy>(`/api/policies/${id}`);
export const listMembers = () => get<Member[]>("/api/members");

// Claims
export function listClaims(params?: { status?: ClaimStatus; policy_id?: number }) {
  const q = new URLSearchParams();
  if (params?.status) q.set("status", params.status);
  if (params?.policy_id) q.set("policy_id", String(params.policy_id));
  const qs = q.toString();
  return get<ClaimSummary[]>(`/api/claims${qs ? `?${qs}` : ""}`);
}
export const getClaim = (id: number) => get<Claim>(`/api/claims/${id}`);
export const getExplanation = (id: number) =>
  get<Explanation>(`/api/claims/${id}/explanation`);
export const submitClaim = (body: ClaimCreate) => post<Claim>("/api/claims", body);

// Lifecycle actions
export const resolveReview = (
  claimId: number,
  lineItemId: number,
  body: { decision: "approve" | "partially_approve" | "deny"; payable_amount?: string; note?: string },
) => post<Claim>(`/api/claims/${claimId}/line-items/${lineItemId}/resolve-review`, body);

export const settleClaim = (id: number) => post<Claim>(`/api/claims/${id}/settle`);
export const readjudicateClaim = (id: number) =>
  post<Claim>(`/api/claims/${id}/readjudicate`);

// Disputes
export const listDisputes = (claimId: number) =>
  get<Dispute[]>(`/api/claims/${claimId}/disputes`);
export const raiseDispute = (
  claimId: number,
  body: { line_item_id?: number; reason_text: string },
) => post<Dispute>(`/api/claims/${claimId}/disputes`, body);
export const resolveDispute = (
  disputeId: number,
  body: { outcome: "upheld" | "overturned"; resolution_text: string; new_payable_amount?: string },
) => post<Dispute>(`/api/disputes/${disputeId}/resolve`, body);

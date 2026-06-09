import Link from "next/link";
import { listClaims } from "@/lib/api";
import { formatDate, formatRupees } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import type { ClaimStatus } from "@/lib/types";

const FILTERS: { label: string; value?: ClaimStatus }[] = [
  { label: "All" },
  { label: "Approved", value: "approved" },
  { label: "Partially approved", value: "partially_approved" },
  { label: "Denied", value: "denied" },
  { label: "Needs review", value: "needs_review" },
];

export default async function ClaimsListPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: ClaimStatus }>;
}) {
  const { status } = await searchParams;
  let claims;
  try {
    claims = await listClaims({ status });
  } catch {
    return <BackendDown />;
  }

  return (
    <div>
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Claims</h1>
          <p className="text-sm text-slate-500">
            Reimbursement claims adjudicated against frozen policy terms.
          </p>
        </div>
        <Link
          href="/claims/new"
          className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          New claim
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => {
          const active = status === f.value || (!status && !f.value);
          const href = f.value ? `/?status=${f.value}` : "/";
          return (
            <Link
              key={f.label}
              href={href}
              className={`rounded-full px-3 py-1 text-sm ${
                active
                  ? "bg-slate-900 text-white"
                  : "bg-white text-slate-600 ring-1 ring-slate-200 hover:bg-slate-50"
              }`}
            >
              {f.label}
            </Link>
          );
        })}
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Claim</th>
              <th className="px-4 py-2 font-medium">Member</th>
              <th className="px-4 py-2 font-medium">Policy</th>
              <th className="px-4 py-2 text-right font-medium">Billed</th>
              <th className="px-4 py-2 text-right font-medium">Payable</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Stage</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {claims.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                  No claims found.
                </td>
              </tr>
            )}
            {claims.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <Link
                    href={`/claims/${c.id}`}
                    className="font-medium text-blue-700 hover:underline"
                  >
                    #{c.id}
                  </Link>
                  <div className="text-xs text-slate-400">{formatDate(c.service_date)}</div>
                </td>
                <td className="px-4 py-3 text-slate-700">{c.member_name}</td>
                <td className="px-4 py-3 font-mono text-xs text-slate-600">{c.policy_number}</td>
                <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                  {formatRupees(c.totals.total_billed)}
                </td>
                <td className="px-4 py-3 text-right font-medium tabular-nums text-green-700">
                  {formatRupees(c.totals.total_payable)}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge value={c.status} />
                </td>
                <td className="px-4 py-3">
                  <StatusBadge value={c.stage} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function BackendDown() {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
      <p className="font-medium">Can&apos;t reach the API.</p>
      <p className="mt-1">
        Start the backend:{" "}
        <code className="font-mono">uv run uvicorn claims.api.app:app --port 8000</code> (after{" "}
        <code className="font-mono">uv run python -m claims.seed</code>).
      </p>
    </div>
  );
}

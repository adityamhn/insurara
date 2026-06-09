import Link from "next/link";
import { listPolicies } from "@/lib/api";
import { formatDate, formatRupees } from "@/lib/format";

export default async function PoliciesPage() {
  let policies;
  try {
    policies = await listPolicies();
  } catch {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800">
        Can&apos;t reach the API. Start the backend on port 8000.
      </div>
    );
  }

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold text-slate-900">Policies</h1>
      <div className="grid gap-4 sm:grid-cols-2">
        {policies.map((p) => {
          const remaining = Number(p.usage.sum_insured_remaining);
          const total = Number(p.usage.sum_insured);
          const pct = total > 0 ? Math.max(0, Math.min(100, (remaining / total) * 100)) : 0;
          return (
            <Link
              key={p.id}
              href={`/policies/${p.id}`}
              className="block rounded-lg border border-slate-200 bg-white p-5 hover:border-slate-300 hover:shadow-sm"
            >
              <div className="flex items-center justify-between">
                <span className="font-mono text-sm text-slate-700">{p.policy_number}</span>
                <span className="text-xs text-slate-400">{p.status}</span>
              </div>
              <div className="mt-1 text-sm text-slate-500">{p.plan_name}</div>
              <div className="mt-3 text-xs text-slate-500">
                {p.members.map((m) => `${m.name} (${m.role})`).join(", ")}
              </div>
              <div className="mt-3">
                <div className="mb-1 flex justify-between text-xs text-slate-500">
                  <span>Sum insured remaining</span>
                  <span className="tabular-nums">
                    {formatRupees(p.usage.sum_insured_remaining)} / {formatRupees(p.usage.sum_insured)}
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-green-500" style={{ width: `${pct}%` }} />
                </div>
              </div>
              <div className="mt-2 text-xs text-slate-400">
                {formatDate(p.start_date)} – {formatDate(p.end_date)}
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

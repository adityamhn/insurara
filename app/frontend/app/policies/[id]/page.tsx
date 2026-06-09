import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getPlan, getPolicy } from "@/lib/api";
import { formatDate, formatRupees, titleCase } from "@/lib/format";
import type { Plan, Policy } from "@/lib/types";

export default async function PolicyDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let policy: Policy;
  let plan: Plan;
  try {
    policy = await getPolicy(Number(id));
    plan = await getPlan(policy.plan_id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const u = policy.usage;
  const siRemaining = Number(u.sum_insured_remaining);
  const siTotal = Number(u.sum_insured);
  const siPct = siTotal > 0 ? Math.max(0, Math.min(100, (siRemaining / siTotal) * 100)) : 0;

  return (
    <div className="space-y-6">
      <div>
        <Link href="/policies" className="text-sm text-slate-500 hover:underline">
          ← All policies
        </Link>
        <h1 className="mt-2 font-mono text-2xl font-semibold text-slate-900">
          {policy.policy_number}
        </h1>
        <p className="text-sm text-slate-500">
          {plan.name} · {formatDate(policy.start_date)} – {formatDate(policy.end_date)} ·{" "}
          {policy.status}
        </p>
      </div>

      {/* Plan terms + usage */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
            Plan terms
          </h2>
          <dl className="space-y-1 text-sm">
            <Term label="Sum insured" value={formatRupees(plan.sum_insured)} />
            <Term label="Deductible" value={formatRupees(plan.deductible)} />
            <Term label="Co-payment" value={`${Number(plan.copay_percent)}%`} />
          </dl>
          <h3 className="mb-1 mt-4 text-xs font-medium uppercase tracking-wide text-slate-500">
            Members
          </h3>
          <ul className="text-sm text-slate-700">
            {policy.members.map((m) => (
              <li key={m.member_id}>
                {m.name} <span className="text-slate-400">({m.role})</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
            Usage this year
          </h2>
          <div className="mb-1 flex justify-between text-sm text-slate-600">
            <span>Sum insured</span>
            <span className="tabular-nums">
              {formatRupees(u.sum_insured_remaining)} remaining of {formatRupees(u.sum_insured)}
            </span>
          </div>
          <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-green-500" style={{ width: `${siPct}%` }} />
          </div>
          <div className="mt-1 text-xs text-slate-400">
            Consumed {formatRupees(u.sum_insured_consumed)}
          </div>

          {Number(plan.deductible) > 0 && (
            <div className="mt-4 text-sm text-slate-600">
              Deductible met: {formatRupees(u.deductible_consumed)} / {formatRupees(plan.deductible)}
            </div>
          )}

          {Object.keys(u.sub_limit_consumed).length > 0 && (
            <div className="mt-4">
              <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                Per-year sub-limits consumed
              </h3>
              <ul className="text-sm text-slate-700">
                {Object.entries(u.sub_limit_consumed).map(([code, amount]) => (
                  <li key={code} className="flex justify-between">
                    <span>{titleCase(code)}</span>
                    <span className="tabular-nums">{formatRupees(amount)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>

      {/* Coverage rules */}
      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-4 py-2 text-sm font-medium text-slate-700">
          Coverage rules
        </div>
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium">Covered</th>
              <th className="px-4 py-2 font-medium">Sub-limit</th>
              <th className="px-4 py-2 font-medium">Waiting</th>
              <th className="px-4 py-2 font-medium">Proportionate</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {plan.coverage_types.map((ct) => (
              <tr key={ct.code}>
                <td className="px-4 py-2 text-slate-700">{ct.name}</td>
                <td className="px-4 py-2">
                  {ct.covered ? (
                    <span className="text-green-700">yes</span>
                  ) : (
                    <span className="text-red-600">excluded</span>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-600">{subLimitLabel(ct)}</td>
                <td className="px-4 py-2 text-slate-600">
                  {ct.waiting_period_days ? `${ct.waiting_period_days}d` : "—"}
                </td>
                <td className="px-4 py-2 text-xs text-slate-500">
                  {ct.triggers_proportionate_deduction
                    ? "triggers"
                    : ct.subject_to_proportionate_deduction
                      ? "subject"
                      : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function subLimitLabel(ct: Plan["coverage_types"][number]): string {
  if (ct.sub_limit_type === "none" || ct.sub_limit_value === null) return "—";
  const basis = ct.sub_limit_basis.replace("per_", "/");
  if (ct.sub_limit_type === "percent_of_si") return `${Number(ct.sub_limit_value)}% of SI ${basis}`;
  return `${formatRupees(ct.sub_limit_value)} ${basis}`;
}

function Term({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-slate-500">{label}</dt>
      <dd className="tabular-nums text-slate-800">{value}</dd>
    </div>
  );
}

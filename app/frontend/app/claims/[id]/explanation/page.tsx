import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getExplanation } from "@/lib/api";
import { formatDelta, formatRupees, titleCase } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import type { Explanation } from "@/lib/types";

export default async function ExplanationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let eob: Explanation;
  try {
    eob = await getExplanation(Number(id));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6 flex items-center justify-between">
        <Link href={`/claims/${eob.claim_id}`} className="text-sm text-slate-500 hover:underline">
          ← Back to claim
        </Link>
        <StatusBadge value={eob.status} />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-6">
        <h1 className="text-xl font-semibold text-slate-900">Explanation of Benefits</h1>
        <p className="mb-6 text-sm text-slate-500">Claim #{eob.claim_id}</p>

        <div className="space-y-5">
          {eob.lines.map((line, idx) => (
            <div key={idx} className="border-b border-slate-100 pb-4 last:border-0">
              <div className="mb-1 flex items-center justify-between">
                <span className="font-medium text-slate-900">
                  {titleCase(line.coverage_type_code)}
                </span>
                <StatusBadge value={line.status} />
              </div>
              <dl className="text-sm">
                <div className="flex justify-between py-0.5 text-slate-600">
                  <dt>Billed</dt>
                  <dd className="tabular-nums">{formatRupees(line.billed_amount)}</dd>
                </div>
                {line.steps.map((s, i) => (
                  <div key={i} className="flex justify-between gap-4 py-0.5">
                    <dt className="text-slate-500">{s.message}</dt>
                    <dd
                      className={`shrink-0 tabular-nums ${
                        Number(s.amount_delta) < 0 ? "text-red-600" : "text-slate-400"
                      }`}
                    >
                      {formatDelta(s.amount_delta)}
                    </dd>
                  </div>
                ))}
                <div className="mt-1 flex justify-between border-t border-slate-200 pt-1 font-medium">
                  <dt className="text-slate-700">Payable</dt>
                  <dd className="tabular-nums text-green-700">{formatRupees(line.payable_amount)}</dd>
                </div>
              </dl>
            </div>
          ))}
        </div>

        <div className="mt-6 space-y-1 rounded-md bg-slate-50 p-4 text-sm">
          <Row label="Total billed" value={eob.totals.total_billed} />
          <Row label="Member bears" value={eob.totals.total_member_borne} />
          <div className="flex justify-between border-t border-slate-200 pt-1 text-base font-semibold">
            <span>Total payable</span>
            <span className="tabular-nums text-green-700">
              {formatRupees(eob.totals.total_payable)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-slate-600">
      <span>{label}</span>
      <span className="tabular-nums">{formatRupees(value)}</span>
    </div>
  );
}

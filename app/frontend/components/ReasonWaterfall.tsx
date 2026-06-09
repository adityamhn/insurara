import { formatDelta, formatRupees } from "@/lib/format";
import type { LineItem } from "@/lib/types";

// The single most important element (SPEC §7.2): billed at top, one row per deduction
// step with its signed amount and human message, payable at the bottom. A reviewer
// should see *why* ₹8,000 became ₹5,000 at a glance.
export function ReasonWaterfall({ line }: { line: LineItem }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60">
      <div className="flex items-center justify-between px-4 py-2 text-sm">
        <span className="text-slate-600">Billed</span>
        <span className="font-medium tabular-nums text-slate-900">
          {formatRupees(line.billed_amount)}
        </span>
      </div>

      {line.reasons.length === 0 ? (
        <div className="border-t border-slate-200 px-4 py-2 text-sm text-slate-500">
          No deductions — covered in full.
        </div>
      ) : (
        <ul className="divide-y divide-slate-200 border-t border-slate-200">
          {line.reasons.map((r, i) => {
            const delta = Number(r.amount_delta);
            return (
              <li key={i} className="flex items-start justify-between gap-4 px-4 py-2 text-sm">
                <div className="min-w-0">
                  <span className="mr-2 inline-block rounded bg-slate-200 px-1.5 py-0.5 font-mono text-[11px] text-slate-700">
                    {r.code}
                  </span>
                  <span className="text-slate-700">{r.message}</span>
                </div>
                <span
                  className={`shrink-0 tabular-nums ${
                    delta < 0 ? "text-red-600" : "text-slate-400"
                  }`}
                >
                  {formatDelta(r.amount_delta)}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      <div className="flex items-center justify-between border-t-2 border-slate-300 px-4 py-2 text-sm">
        <span className="font-medium text-slate-700">Payable</span>
        <span className="font-semibold tabular-nums text-green-700">
          {formatRupees(line.payable_amount)}
        </span>
      </div>
      {Number(line.member_share) > 0 && (
        <div className="flex items-center justify-between px-4 pb-2 text-xs text-slate-500">
          <span>Member bears</span>
          <span className="tabular-nums">{formatRupees(line.member_share)}</span>
        </div>
      )}
    </div>
  );
}

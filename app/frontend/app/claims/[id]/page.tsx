import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getClaim } from "@/lib/api";
import { formatDate, formatDateTime, formatRupees, titleCase } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { ReasonWaterfall } from "@/components/ReasonWaterfall";
import type { Claim, LineItem } from "@/lib/types";
import {
  AdjusterPanel,
  RaiseDisputeButton,
  ReadjudicateButton,
  ResolveDisputePanel,
  SettleButton,
} from "./actions";

const DECIDED: LineItem["status"][] = ["approved", "partially_approved", "denied"];

export default async function ClaimDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  let claim: Claim;
  try {
    claim = await getClaim(Number(id));
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const hasReview = claim.line_items.some((li) => li.status === "under_review");
  const settled = claim.stage === "settled";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <Link href="/" className="text-sm text-slate-500 hover:underline">
          ← All claims
        </Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Claim #{claim.id}</h1>
            <p className="text-sm text-slate-500">
              {claim.member_name} · <span className="font-mono">{claim.policy_number}</span> ·
              service {formatDate(claim.service_date)} · snapshot #{claim.policy_snapshot_id}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge value={claim.status} />
            <StatusBadge value={claim.stage} />
          </div>
        </div>
      </div>

      {/* Totals + claim actions */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex gap-8">
          <Total label="Billed" value={claim.totals.total_billed} />
          <Total label="Payable" value={claim.totals.total_payable} accent />
          <Total label="Member bears" value={claim.totals.total_member_borne} />
        </div>
        <div className="flex items-center gap-2">
          <Link
            href={`/claims/${claim.id}/explanation`}
            className="rounded-md px-3 py-1.5 text-sm font-medium text-blue-700 ring-1 ring-blue-200 hover:bg-blue-50"
          >
            View EOB
          </Link>
          {!settled && <ReadjudicateButton claimId={claim.id} />}
          {!settled && <SettleButton claimId={claim.id} disabled={hasReview} />}
        </div>
      </div>

      {/* Line items + waterfalls */}
      <section className="space-y-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Line items
        </h2>
        {claim.line_items.map((li) => (
          <div key={li.id} className="rounded-lg border border-slate-200 bg-white p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div>
                <span className="font-medium text-slate-900">{titleCase(li.coverage_type_code)}</span>
                {li.description && (
                  <span className="ml-2 text-sm text-slate-500">{li.description}</span>
                )}
                {(li.diagnosis_code || li.provider_name) && (
                  <div className="text-xs text-slate-400">
                    {li.diagnosis_code && <span>dx {li.diagnosis_code}</span>}
                    {li.diagnosis_code && li.provider_name && " · "}
                    {li.provider_name}
                  </div>
                )}
              </div>
              <StatusBadge value={li.status} />
            </div>

            <ReasonWaterfall line={li} />

            {li.status === "under_review" && <AdjusterPanel claimId={claim.id} line={li} />}
            {!settled && DECIDED.includes(li.status) && (
              <div className="mt-2">
                <RaiseDisputeButton claimId={claim.id} lineItemId={li.id} />
              </div>
            )}
          </div>
        ))}
      </section>

      {/* Disputes */}
      {claim.disputes.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Disputes</h2>
          {claim.disputes.map((d) => (
            <div key={d.id} className="rounded-lg border border-purple-200 bg-purple-50/50 p-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-700">
                  Dispute #{d.id}
                  {d.line_item_id ? ` · line ${d.line_item_id}` : " · claim-level"}
                </span>
                <StatusBadge value={d.state} />
              </div>
              <p className="mt-1 text-sm text-slate-600">“{d.reason_text}”</p>
              {d.resolution_text && (
                <p className="mt-1 text-sm text-slate-500">Resolution: {d.resolution_text}</p>
              )}
              {!settled && <ResolveDisputePanel dispute={d} />}
            </div>
          ))}
        </section>
      )}

      {/* Activity stream */}
      <section>
        <h2 className="mb-2 text-sm font-medium uppercase tracking-wide text-slate-500">
          Activity
        </h2>
        <ol className="space-y-1 rounded-lg border border-slate-200 bg-white p-4 text-sm">
          {claim.decision_logs.map((log, i) => (
            <li key={i} className="flex gap-3">
              <span className="shrink-0 text-slate-400">{formatDateTime(log.timestamp)}</span>
              <span className="shrink-0 rounded bg-slate-100 px-1.5 text-xs text-slate-500">
                {log.actor}
              </span>
              <span className="text-slate-700">{log.message}</span>
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}

function Total({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`text-lg font-semibold tabular-nums ${accent ? "text-green-700" : "text-slate-900"}`}>
        {formatRupees(value)}
      </div>
    </div>
  );
}

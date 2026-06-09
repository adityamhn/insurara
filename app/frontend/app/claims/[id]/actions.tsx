"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  raiseDispute,
  readjudicateClaim,
  resolveDispute,
  resolveReview,
  settleClaim,
} from "@/lib/api";
import type { Dispute, LineItem } from "@/lib/types";

function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

function Err({ message }: { message: string | null }) {
  if (!message) return null;
  return <p className="mt-1 text-xs text-red-600">{message}</p>;
}

const btn = "rounded-md px-3 py-1.5 text-sm font-medium disabled:opacity-50";

/** Adjuster panel for an under_review line — confirm/reduce/deny the rules-allowed amount. */
export function AdjusterPanel({ claimId, line }: { claimId: number; line: LineItem }) {
  const { busy, error, run } = useAction();
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");

  return (
    <div className="mt-3 rounded-md border border-blue-200 bg-blue-50 p-3">
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-blue-800">
        Adjuster review · rules-allowed ₹{line.payable_amount}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="w-40 rounded-md border border-slate-300 px-2 py-1 text-sm"
          placeholder="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          className={`${btn} bg-green-600 text-white hover:bg-green-700`}
          disabled={busy}
          onClick={() =>
            run(() => resolveReview(claimId, line.id, { decision: "approve", note: note || undefined }))
          }
        >
          Approve
        </button>
        <span className="flex items-center gap-1">
          <input
            className="w-28 rounded-md border border-slate-300 px-2 py-1 text-sm"
            placeholder="₹ amount"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <button
            className={`${btn} bg-amber-500 text-white hover:bg-amber-600`}
            disabled={busy || !amount}
            onClick={() =>
              run(() =>
                resolveReview(claimId, line.id, {
                  decision: "partially_approve",
                  payable_amount: amount,
                  note: note || undefined,
                }),
              )
            }
          >
            Partially approve
          </button>
        </span>
        <button
          className={`${btn} bg-red-600 text-white hover:bg-red-700`}
          disabled={busy}
          onClick={() =>
            run(() => resolveReview(claimId, line.id, { decision: "deny", note: note || undefined }))
          }
        >
          Deny
        </button>
      </div>
      <Err message={error} />
    </div>
  );
}

/** Raise a dispute on a decided line. */
export function RaiseDisputeButton({ claimId, lineItemId }: { claimId: number; lineItemId: number }) {
  const { busy, error, run } = useAction();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");

  if (!open) {
    return (
      <button
        className="text-xs text-slate-500 underline hover:text-purple-700"
        onClick={() => setOpen(true)}
      >
        Raise dispute
      </button>
    );
  }
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        className="w-56 rounded-md border border-slate-300 px-2 py-1 text-sm"
        placeholder="Reason for dispute"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
      />
      <button
        className={`${btn} bg-purple-600 text-white hover:bg-purple-700`}
        disabled={busy || !reason}
        onClick={() =>
          run(async () => {
            await raiseDispute(claimId, { line_item_id: lineItemId, reason_text: reason });
            setOpen(false);
          })
        }
      >
        Submit
      </button>
      <button className="text-xs text-slate-400" onClick={() => setOpen(false)}>
        cancel
      </button>
      <Err message={error} />
    </div>
  );
}

/** Resolve an open dispute: uphold or overturn (optionally at a corrected amount). */
export function ResolveDisputePanel({ dispute }: { dispute: Dispute }) {
  const { busy, error, run } = useAction();
  const [text, setText] = useState("");
  const [amount, setAmount] = useState("");

  if (dispute.state !== "raised" && dispute.state !== "under_review") return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        className="w-56 rounded-md border border-slate-300 px-2 py-1 text-sm"
        placeholder="Resolution note"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <button
        className={`${btn} bg-slate-700 text-white hover:bg-slate-800`}
        disabled={busy || !text}
        onClick={() => run(() => resolveDispute(dispute.id, { outcome: "upheld", resolution_text: text }))}
      >
        Uphold
      </button>
      <input
        className="w-28 rounded-md border border-slate-300 px-2 py-1 text-sm"
        placeholder="₹ (optional)"
        inputMode="decimal"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <button
        className={`${btn} bg-green-600 text-white hover:bg-green-700`}
        disabled={busy || !text}
        onClick={() =>
          run(() =>
            resolveDispute(dispute.id, {
              outcome: "overturned",
              resolution_text: text,
              new_payable_amount: amount || undefined,
            }),
          )
        }
      >
        Overturn
      </button>
      <Err message={error} />
    </div>
  );
}

/** Settle the claim (pay out + advance usage counters). */
export function SettleButton({ claimId, disabled }: { claimId: number; disabled: boolean }) {
  const { busy, error, run } = useAction();
  return (
    <span>
      <button
        className={`${btn} bg-emerald-600 text-white hover:bg-emerald-700`}
        disabled={busy || disabled}
        title={disabled ? "Resolve all reviews first" : undefined}
        onClick={() => run(() => settleClaim(claimId))}
      >
        Settle claim
      </button>
      <Err message={error} />
    </span>
  );
}

/** Re-run the engine from the frozen snapshot (reset). */
export function ReadjudicateButton({ claimId }: { claimId: number }) {
  const { busy, error, run } = useAction();
  return (
    <span>
      <button
        className={`${btn} bg-white text-slate-600 ring-1 ring-slate-300 hover:bg-slate-50`}
        disabled={busy}
        onClick={() => run(() => readjudicateClaim(claimId))}
      >
        Re-adjudicate
      </button>
      <Err message={error} />
    </span>
  );
}

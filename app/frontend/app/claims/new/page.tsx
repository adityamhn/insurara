"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getPlan, listPolicies, submitClaim } from "@/lib/api";
import type { CoverageType, LineItemCreate, Policy } from "@/lib/types";

type Row = LineItemCreate;

const emptyRow = (code: string): Row => ({
  coverage_type_code: code,
  billed_amount: "",
  service_days: 1,
  diagnosis_code: "",
  provider_name: "",
  description: "",
});

export default function NewClaimPage() {
  const router = useRouter();
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [policyId, setPolicyId] = useState<number | "">("");
  const [memberId, setMemberId] = useState<number | "">("");
  const [serviceDate, setServiceDate] = useState("");
  const [coverageTypes, setCoverageTypes] = useState<CoverageType[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    listPolicies().then(setPolicies).catch(() => setError("Could not load policies — is the API running?"));
  }, []);

  const policy = policies.find((p) => p.id === policyId);

  // When the policy changes, load its plan's coverage types and reset dependent fields.
  // Done in the event handler (not a useEffect) to avoid cascading effect renders.
  async function onPolicyChange(value: string) {
    const id = value ? Number(value) : "";
    setPolicyId(id);
    const chosen = policies.find((p) => p.id === id);
    if (!chosen) {
      setCoverageTypes([]);
      setRows([]);
      setMemberId("");
      return;
    }
    setMemberId(chosen.members[0]?.member_id ?? "");
    setServiceDate((d) => d || chosen.start_date);
    const plan = await getPlan(chosen.plan_id);
    setCoverageTypes(plan.coverage_types);
    setRows([emptyRow(plan.coverage_types[0]?.code ?? "")]);
  }

  function updateRow(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (policyId === "" || memberId === "") return;
    const form = e.currentTarget as HTMLFormElement;
    const submittedServiceDate = String(new FormData(form).get("service_date") ?? serviceDate);
    setSubmitting(true);
    try {
      const claim = await submitClaim({
        policy_id: policyId,
        member_id: memberId,
        service_date: submittedServiceDate,
        line_items: rows.map((r) => ({
          coverage_type_code: r.coverage_type_code,
          billed_amount: r.billed_amount,
          service_days: Number(r.service_days) || 1,
          diagnosis_code: r.diagnosis_code || null,
          provider_name: r.provider_name || null,
          description: r.description || null,
        })),
      });
      router.push(`/claims/${claim.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission failed");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-6 text-2xl font-semibold text-slate-900">New claim</h1>

      {error && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-800">
          {error}
        </div>
      )}

      <form onSubmit={onSubmit} className="space-y-6">
        <section className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-white p-5 sm:grid-cols-3">
          <Field label="Policy">
            <select
              required
              className="input"
              value={policyId}
              onChange={(e) => onPolicyChange(e.target.value)}
            >
              <option value="">Select…</option>
              {policies.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.policy_number} — {p.plan_name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Member">
            <select
              required
              className="input"
              value={memberId}
              disabled={!policy}
              onChange={(e) => setMemberId(e.target.value ? Number(e.target.value) : "")}
            >
              {policy?.members.map((m) => (
                <option key={m.member_id} value={m.member_id}>
                  {m.name} ({m.role})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Service date">
            <input
              type="date"
              name="service_date"
              required
              className="input"
              value={serviceDate}
              min={policy?.start_date}
              max={policy?.end_date}
              onInput={(e) => setServiceDate(e.currentTarget.value)}
              onChange={(e) => setServiceDate(e.target.value)}
            />
          </Field>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-5">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-medium text-slate-900">Line items</h2>
            <button
              type="button"
              disabled={!coverageTypes.length}
              onClick={() => setRows((rs) => [...rs, emptyRow(coverageTypes[0]?.code ?? "")])}
              className="rounded-md bg-slate-100 px-2.5 py-1 text-sm text-slate-700 hover:bg-slate-200 disabled:opacity-50"
            >
              + Add line
            </button>
          </div>

          {!policy && <p className="text-sm text-slate-500">Select a policy first.</p>}

          <div className="space-y-3">
            {rows.map((row, i) => (
              <div key={i} className="grid grid-cols-1 gap-2 rounded-md bg-slate-50 p-3 sm:grid-cols-12">
                <div className="sm:col-span-3">
                  <select
                    className="input"
                    value={row.coverage_type_code}
                    onChange={(e) => updateRow(i, { coverage_type_code: e.target.value })}
                  >
                    {coverageTypes.map((ct) => (
                      <option key={ct.code} value={ct.code}>
                        {ct.name}
                        {ct.covered ? "" : " (excluded)"}
                      </option>
                    ))}
                  </select>
                </div>
                <input
                  className="input sm:col-span-2"
                  placeholder="Billed ₹"
                  inputMode="decimal"
                  value={row.billed_amount}
                  onChange={(e) => updateRow(i, { billed_amount: e.target.value })}
                  required
                />
                <input
                  className="input sm:col-span-1"
                  type="number"
                  min={1}
                  title="Service days"
                  value={row.service_days}
                  onChange={(e) => updateRow(i, { service_days: Number(e.target.value) })}
                />
                <input
                  className="input sm:col-span-2"
                  placeholder="Diagnosis"
                  value={row.diagnosis_code ?? ""}
                  onChange={(e) => updateRow(i, { diagnosis_code: e.target.value })}
                />
                <input
                  className="input sm:col-span-3"
                  placeholder="Provider"
                  value={row.provider_name ?? ""}
                  onChange={(e) => updateRow(i, { provider_name: e.target.value })}
                />
                <button
                  type="button"
                  onClick={() => setRows((rs) => rs.filter((_, idx) => idx !== i))}
                  disabled={rows.length === 1}
                  className="text-sm text-slate-400 hover:text-red-600 disabled:opacity-40 sm:col-span-1"
                  aria-label="Remove line"
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </section>

        <div className="flex justify-end gap-3">
          <button
            type="submit"
            disabled={submitting || !policy || rows.length === 0}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {submitting ? "Adjudicating…" : "Submit & adjudicate"}
          </button>
        </div>
      </form>

      <style>{`.input{width:100%;border:1px solid #cbd5e1;border-radius:0.375rem;padding:0.375rem 0.5rem;font-size:0.875rem;background:#fff}`}</style>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      {children}
    </label>
  );
}

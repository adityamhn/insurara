import { titleCase } from "@/lib/format";

// Consistent status colors across claims, line items, and disputes (SPEC §7.2).
const STYLES: Record<string, string> = {
  approved: "bg-green-100 text-green-800 ring-green-600/20",
  paid: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  partially_approved: "bg-amber-100 text-amber-800 ring-amber-600/20",
  denied: "bg-red-100 text-red-800 ring-red-600/20",
  needs_review: "bg-blue-100 text-blue-800 ring-blue-600/20",
  under_review: "bg-blue-100 text-blue-800 ring-blue-600/20",
  disputed: "bg-purple-100 text-purple-800 ring-purple-600/20",
  // claim stages
  submitted: "bg-slate-100 text-slate-700 ring-slate-600/20",
  under_adjudication: "bg-blue-100 text-blue-800 ring-blue-600/20",
  decided: "bg-slate-100 text-slate-700 ring-slate-600/20",
  settled: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  closed: "bg-slate-200 text-slate-700 ring-slate-600/20",
  // dispute states
  raised: "bg-amber-100 text-amber-800 ring-amber-600/20",
  upheld: "bg-slate-100 text-slate-700 ring-slate-600/20",
  overturned: "bg-green-100 text-green-800 ring-green-600/20",
};

export function StatusBadge({ value }: { value: string | null }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const style = STYLES[value] ?? "bg-slate-100 text-slate-700 ring-slate-600/20";
  return (
    <span
      className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
    >
      {titleCase(value)}
    </span>
  );
}

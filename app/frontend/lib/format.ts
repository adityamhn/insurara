// Display formatting only. Money arrives as exact decimal strings; we parse to Number
// purely to add Indian-style grouping for the eye — never for arithmetic.

export function formatRupees(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  return `₹${n.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

// A signed delta (reductions are negative) e.g. "−₹3,000.00".
export function formatDelta(value: string): string {
  const n = Number(value);
  if (Number.isNaN(n) || n === 0) return "—";
  const sign = n < 0 ? "−" : "+";
  return `${sign}${formatRupees(Math.abs(n).toFixed(2))}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" });
}

export function formatDateTime(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

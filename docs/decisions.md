# Decisions & Trade-offs

Two parts: the **design decisions** (the shape of the domain and why), and the
**implementation notes** (concrete calls made while building — including where the
requirements were ambiguous or a bug forced a choice).

---

## Design decisions

| Decision | Why |
|----------|-----|
| **One line of business (health), with clean seams** — not a generic multi-line framework | A fully generic multi-product framework is overkill here; keep the clean seam (`Claim → LineItem` adjudicated by a configurable rule set) without the cost of real genericity. |
| **Coverage rules as data (a decision table)** — rows + an ordered pipeline, not `if/else`, not a DSL | Inspectable, testable, and configurable — the sweet spot between rigid conditionals and an over-built DSL. This is the centerpiece of the system. |
| **3-level coverage model** `CoveragePlan → CoverageType → per-Policy values` | The template-vs-instance split (reusable rules vs. per-customer config) is the valuable idea; deeper layering buys nothing at this scale. |
| **Two state machines; claim status DERIVED from line items; claim has stage + status** | The derived-parent-from-children mechanic is exactly the "partial approval" problem worth modelling. |
| **Independent per-line adjudication; proportionate deduction as an Indian reduction reason** | Answers "3 covered, 1 denied, 1 needs review"; proportionate deduction makes the demo domain-rich. |
| **Explanations = a pipeline of reasons (append-only log)** | The accumulated `Reason[]` *is* the EOB; not bolted on. |
| **Policy snapshots** — adjudicate against frozen terms | Later edits to a policy can't change a past claim's outcome. |
| **`Claim → LineItem`; outcome per line, mapped to a coverage type** | Matches the insurance vocabulary. |
| **Single payable per line; no reserves/payments; keep the auto-decide-vs-review threshold** | Reserves serve long-running P&C claims, not health reimbursement; the human-review split is the realistic, demoable part. |
| **Sensitive data documented, not enforced** | Fields tagged in the schema; column-encryption + reader-role access described, not built (out of scope). |
| **Member separate from their role on a policy** → family floater | A `PolicyMember` join with a role; multiple members share one sum insured. |
| **Next.js + FastAPI REST, a real web app** | A demonstrable product with a clean API boundary. |

**Simplifications taken:** single line of business; 3-level coverage; single payable (no
reserves/payments split); sensitivity documented not enforced; no fraud engine / OCR /
notifications / auth.

**Richer than a generic system (kept):** Sum Insured, per-service sub-limits (esp. room
rent), **proportionate deduction** (IRDAI 2024), co-payment, deductible, waiting periods,
exclusions — these make the pipeline and the explanations meaningful.

---

## Implementation notes

### Adjudication pipeline ordering (two natural orderings conflict)
The pipeline runs: coverage → waiting → **sub-limit cap** → **proportionate deduction** →
**sum-insured / per-year balance** → deductible → co-payment → needs-review → finalize. The
one genuinely debatable point is where proportionate deduction sits relative to the
sum-insured ceiling: scale the associated charges first, or apply the overall ceiling first?

**Call:** I cap each line to its sub-limit, then proportionate-scale the associated charges,
then treat the sum insured as the *final* ceiling — the domain-sensible reading, since SI is
the overall pool cap and should bound whatever the per-category rules allow. The worked
example (₹64,000 → ₹41,400) yields the same result either way; the orderings only diverge
when a room-rent breach and SI exhaustion co-occur in one claim. Implemented as a per-line
pass A (coverage/waiting/sub-limit) → claim-level proportionate pass → claim-level balance
pass.

### Cross-line steps run as claim-level passes
Proportionate deduction is cross-line (room-rent breach scales *other* lines), and the
deductible is a single per-claim amount. Both are claim-level passes, not per-line steps.
The per-year sub-limit / sum-insured balance pass threads in-claim consumption across lines
so a claim can't exceed a limit by splitting an amount across line items.

### Deductible: claim-level, once, after the proportionate pass
The deductible is a single per-claim amount, so it's applied once at claim level after the
proportionate pass (the cleaner of the orderings). Co-payment is applied **per line** —
mathematically identical to a claim-level copay (it's linear) and keeps each line's waterfall
self-contained.

### Needs-review runs LAST (step 8), and the adjuster is bounded by the computed amount
**This started as a bug.** The first cut routed high-value lines to `under_review` *before*
the sub-limit cap, so the cap was never computed and `resolve_review` let an adjuster
approve the full billed amount — e.g. room rent ₹1,50,000 against a ₹5,000 cap. **Fix:**
needs-review now runs after every automatic reduction; the routed line keeps its
fully-computed, rules-capped payable, and `resolve_review` lets the adjuster confirm or
reduce that amount but **never exceed it**. (Regression-tested at engine and API level.)

### Proportionate deduction is data-driven, IRDAI-2024 exact
`ratio = cap / billed_room_rent`; only lines flagged `subject_to_proportionate_deduction`
are scaled. Pharmacy, diagnostics, and implants carry `subject = false` per IRDAI 2024 — the
exclusion list is data on the rows, never hardcoded in the engine.

### `under_review` payable & money precision
A routed line's stored payable is the provisional rules-allowed amount (the adjuster's
ceiling). Money is `Decimal` 2 dp end to end; SQLite stores it as TEXT (a `Money` type
decorator) because SQLAlchemy `Numeric` round-trips through float on SQLite; the boundary
refuses Python floats outright. Snapshots are stored as pydantic JSON so Decimals round-trip
exactly.

### Settlement & lifecycle guards
Counters increment on settlement, not adjudication. Settlement is blocked (409) if any line
is `under_review`, any line is `disputed`, or any dispute is open — so a claim can't reach
`settled` with unresolved state. Disputes are handled before settlement (a `paid` line has
no `disputed` edge in the line-item machine; a settled claim is closed to disputes).

### `readjudicate` is a deterministic reset
Re-runs the engine from the frozen snapshot and overwrites stored results, discarding manual
review/dispute overrides. Useful for the demo; documented as such.

### Persistence: no Alembic
Plain SQLAlchemy `create_all` + a seed script. A SQLite take-home prioritizes "clone and
run"; migrations buy nothing when the schema ships in one cut and the DB regenerates from the
seed. The URL is swappable (`CLAIMS_DB_URL`) so Postgres is a config change.

### Frontend data flow
Server Components fetch reads (`no-store`); Client Components do mutations then
`router.refresh()`. No SWR/React Query — fewer deps, and the server-render keeps the
reason-waterfall fast and SEO-trivial. Money rendered from the exact decimal strings, never
parsed to float for arithmetic.

---

## Assumptions about the domain
- A policy year aligns with the policy period; usage counters are per policy-year.
- Sub-limit accumulation across claims applies only to `per_year` sub-limits
  (`per_day`/`per_claim` reset).
- The high-value review threshold is plan-configurable (default ₹1,00,000); it is a stand-in
  for real triage rules, not ML.
- Service date must fall within the policy period and the policy must be `in_force`.

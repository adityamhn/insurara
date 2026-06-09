# Self-Review

An honest assessment — what's solid, what's thin, and what I'd do with more time.

## What's strong

- **The adjudication engine.** Pure, deterministic, DB-free
  (`app/backend/claims/engine/`), and the most thoroughly tested part: the §4.4 worked
  example (₹64,000 → ₹41,400), one test per pipeline step, proportionate deduction with the
  IRDAI-2024 exclusions, sum-insured / per-year sub-limit exhaustion, the state-derivation
  rule, and the money invariant. Tests encode domain rules, not HTTP status codes.
- **Proportionate deduction** is the most domain-accurate piece: data-driven via the
  `subject_to_proportionate_deduction` flag (not a hardcoded list), ratio off billed room
  rent, IRDAI-2024 exclusions for pharmacy/diagnostics/implants.
- **Explanations as a byproduct.** Every reduction emits an ordered `Reason`; the same data
  drives the API `/explanation` and the UI reason-waterfall. Nothing is reconstructed.
- **Snapshot isolation** is real and tested — later policy edits provably don't change past
  claims.
- **Lifecycle integrity.** Claim status is always derived from line items; settlement is
  guarded against pending review and open disputes (can't reach `settled` with unresolved
  state).
- **Two independent domain reviews** (fresh-context agent passes) ran against the engine and
  API; both findings they surfaced as Critical were real and are fixed (see below).

## What's rough / deliberately simplified

- **Sequential settlement only (concurrency).** Counters are snapshotted at creation and
  applied on settlement; two claims opened before either settles both see the same headroom
  and could together over-consume the Sum Insured. This is the SPEC §3.3 stated
  simplification. A production fix needs row-level locks or a settlement-time
  `consumed + payable ≤ sum_insured` re-check (returning 409). Documented in
  `service/snapshot.py`.
- **The §4.2-vs-§4.3 ordering ambiguity.** The spec contradicts itself on whether the
  sum-insured balance check runs before or after proportionate deduction. I chose §4.2's
  explicit numbering (proportionate before the SI ceiling) and documented it; a reviewer
  could reasonably want the other order. It only matters when a room-rent breach and SI
  exhaustion collide in one claim — untested in combination beyond reasoning.
- **Needs-review is a flat threshold**, not real triage/ML. It's a stand-in for the
  auto-vs-human split; one realistic trigger, plan-configurable.
- **Auth, encryption, RBAC: not built** (out of scope). Sensitive fields are tagged in the
  schema with the intended controls described, not enforced.
- **No frontend automated tests.** The UI was verified by clicking through the running app
  (browser agent + screenshots of the waterfall) and by `npm run build` + lint, but there
  are no Playwright/RTL tests. The backend is where the test value lives.
- **N+1 in the claims list.** `claim_summary_out` lazy-loads `policy`/`member` per row; fine
  for the demo's data volume, but would need `selectinload` at scale. No pagination either.
- **Deductible ordering across lines** is "first lines until exhausted" — correct in total,
  but which specific line absorbs it is order-dependent; acceptable since the claim total is
  what matters.
- **Single currency / locale** (INR), and `service_days` is a simple multiplier for per-day
  sub-limits (no date-range modelling of a hospital stay).

## Bugs found and fixed during the build (honesty about the process)

- **Overpayment hole (Critical, B4 in decisions).** Needs-review originally ran before the
  sub-limit cap, so an adjuster could approve a high-value line above its cap. Fixed: review
  runs last; the adjuster is bounded by the engine's computed amount. Regression-tested.
- **Reasons orphaned on insert.** Reasons were first created with `line_item_id=row.id`
  before the row was flushed (id still `None`); switched to appending via the relationship.
- **Money default as string `"0"`** broke arithmetic on freshly-created policies; changed
  the column defaults to `Decimal`.
- **Per-year sub-limit bucket over-debited** when the SI check later reduced a line; now
  debits both balances by the final payable.
- **Settling claims with open disputes** was possible; now blocked (409) in the API.
- **New-claim service date** could submit the policy's default start date instead of the
  entered value; the form now reads the named field as the source of truth.

## What I'd do next with more time
1. Settlement-time limit re-check + optimistic locking for true concurrency safety.
2. A few API tests for the §4.2/§4.3 ordering edge (breach + exhaustion together).
3. Eager-loading + pagination on the claims list.
4. A small Playwright suite for the three core UI flows.
5. Resolve the ordering ambiguity with the assignment authors rather than choosing.

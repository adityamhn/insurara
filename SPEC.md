# Claims Processing System — Engineering Build Specification

**Audience:** Engineering team (Claude Code) building the system from scratch.
**Domain:** Indian health insurance, reimbursement claims.
**Stack:** Next.js frontend, Python + FastAPI backend, REST architecture.
**Status:** Authoritative build spec. Read this top to bottom before writing code.

---

## 0. How to read this document

This spec is organized so you can build in order:

1. **Context & scope** — what we're building and what we're deliberately not.
2. **Design decisions** — every non-obvious choice, with rationale, so you don't re-litigate them.
3. **Domain model** — entities, relationships, the two state machines.
4. **The adjudication engine** — the heart of the system; the rule representation and the pipeline.
5. **API design** — every REST endpoint, request/response shapes.
6. **Data layer** — schema, seed data.
7. **Frontend** — pages, components, flows.
8. **Build sequence** — the order to implement things so the system is demoable at each step.
9. **Seed scenarios** — the exact data that makes the demo tell a story.

Defined terms (Sum Insured, Sub-limit, Proportionate Deduction, etc.) are in the glossary at the end. When a term is capitalized in this doc, it has a precise meaning defined there.

The design borrows heavily from ServiceNow's Financial Services Operations (FSO) claims data model, simplified for scope. Where a decision cites "ServiceNow," that means we adopted their proven pattern; where it cites "simplified," we deliberately took a lighter path.

---

## 1. Context & scope

### 1.1 What the system does

An insurance member incurs a medical expense, pays out of pocket, and submits a **reimbursement claim** with one or more **line items** (each line item is a billed expense — room charges, surgery, pharmacy, diagnostics, etc.). The system must:

- Accept the claim submission against the member's policy.
- **Adjudicate each line item** against the policy's coverage rules — deciding, per line item, whether it is covered and how much is payable.
- Track both the claim and each line item through their lifecycle states.
- Produce a **human-readable explanation for every decision** (the equivalent of an Explanation of Benefits / deduction breakdown).
- Allow members to **dispute** a decision.

This is the Indian **reimbursement** flow specifically (member pays first, claims back later), not cashless/pre-authorization. That means adjudication happens entirely after submission — there is no real-time hospital round-trip to model.

### 1.2 In scope

- Submitting a claim with line items.
- Adjudicating line items against coverage rules (the core).
- Claim and line-item lifecycle state management.
- Explanation generation for every coverage decision.
- Members disputing decisions.
- A web UI (Next.js) and REST API (FastAPI) to demonstrate all of the above.

### 1.3 Explicitly OUT of scope

Do not build these. They are adjacent real-world concerns that add no evaluation value and cost time:

- User registration, login, authentication, authorization. (We *document* data-sensitivity intent — see Decision 10 — but do not implement access control.)
- Policy purchase / enrollment flows.
- Member or provider account management.
- Email / SMS notifications.
- Reporting dashboards / analytics.
- Admin panels for managing policies/members/providers (we seed this data directly).
- Multi-tenant or role-based access control.
- Reserves vs. payments separation, fraud scoring engines, document OCR. (See Decisions 9 and the simplifications.)

### 1.4 Personas (for UI framing only — not auth roles)

- **Member** — submits claims, views decisions/explanations, raises disputes.
- **Adjuster / Processor** — internal view: sees the adjudication breakdown, can route line items needing review, resolves disputes. (One combined internal view is fine; do not build separate role logins.)

---

## 2. Design decisions

Each decision states the choice, the ServiceNow reference where relevant, and the rationale. These are settled — build to them.

### Decision 1 — Generic framework vs. single line of business → **Lean simple: health only, with clean seams**

We build **one line of business (Indian health reimbursement)**, but structure the domain so the coverage model and rule engine are not hardcoded to health-specific `if` statements. ServiceNow ships a fully generic framework plus per-line-of-business extensions; that genericity is over-engineering for our scope. We keep the *seam* (a `Claim` has generic `LineItem`s adjudicated by a configurable rule set) without building a multi-line-of-business framework. **Rationale:** demonstrates clean decomposition without the cost of real genericity.

### Decision 2 — Coverage rule representation → **Decision-table-style rules as data (ServiceNow)**

Coverage and adjudication rules are stored as **data rows evaluated by an engine**, not as hardcoded conditionals and not as a full DSL. This is ServiceNow's decision-table pattern. Each rule is a row: conditions → outcome + reason. **Rationale:** this is the centerpiece of the assignment ("how do you structure coverage logic?"). Decision tables are the sweet spot — configurable, inspectable, testable, and demoable — between rigid `if/else` and an over-built DSL. See Section 4 for the exact representation.

### Decision 3 — Coverage data model → **Template/instance split, simplified to 3 levels**

ServiceNow uses Product Model → Coverage Specification → Coverage Type → Coverage Option, instantiated onto a Policy. We **collapse to three levels**: `CoveragePlan` (template) → `CoverageType` (with limit/sub-limit/copay attributes) → instantiated per `Policy` as the policy's coverage values. **Rationale:** the template-vs-instance separation is the valuable idea (reusable rules vs. per-customer config); the separate "coverage specification" object adds indirection that buys nothing at our scale.

### Decision 4 — Two state machines → **Separate claim & line-item machines; claim state DERIVED from line items; two-axis (stage + status) for the claim**

The **claim** carries a coarse `stage` plus a finer `status` (ServiceNow's two-axis model). Each **line item** has its own independent state machine. The claim's state is **computed from** its line items' states — this derivation is the core of the "partial approval" problem. We keep Indian-domain terminal states (e.g. `partially_approved`, `disputed`). **Rationale:** assignment explicitly flags the claim-vs-line-item distinction; deriving the parent from children is the exact mechanism being tested. See Section 3.4.

### Decision 5 — Partial approvals → **Independent per-line-item adjudication; claim status derived from the mix; proportionate deduction as an Indian-specific reduction reason**

Each line item adjudicates independently and may land in approved / denied / partially-approved / needs-review. The claim status is derived from the set. We additionally implement **proportionate deduction** (Indian rule: when room rent exceeds the room-rent sub-limit, associated charges scale down proportionally), which is a case where a *covered* line item is still only partly paid. **Rationale:** directly answers the "3 covered, 1 denied, 1 needs review" scenario, and the proportionate-deduction rule makes the demo richer than a generic system.

### Decision 6 — Explanations → **Pipeline-of-reasons generation, stored as an append-only decision log**

Adjudication is modeled as a **pipeline of discrete steps**; each step that affects the outcome emits a structured `Reason` record. These accumulate into an append-only log per line item and per claim (ServiceNow's activity-stream pattern). The collected reasons *are* the explanation (the EOB / deduction breakdown). **Rationale:** satisfies "explanation capability" cleanly — explanations are a byproduct of how adjudication runs, not a bolted-on afterthought.

### Decision 7 — Retroactive policy changes → **Policy snapshots (ServiceNow)**

When a claim is created, we **snapshot the policy terms onto the claim**, keyed to the claim's service/loss date. Adjudication runs against the snapshot, never the live policy. **Rationale:** cleanly handles the "retroactive changes" edge case — later policy edits don't change past claims. Strong maturity signal.

### Decision 8 — Line-item / itemization model → **`Claim → LineItem`; financial outcome attaches per line item, mapped to a coverage type**

We use the assignment's own vocabulary: a `Claim` contains `LineItem`s. Each line item references a `CoverageType` (what kind of expense it is) and the payable amount is computed against that coverage's rules. **Rationale:** matches the brief's language; ServiceNow's "incident → itemized loss" is the same idea with heavier naming.

### Decision 9 — Financial model → **Single payable amount per line item; NO reserves/payments split; KEEP the auto-approve-vs-route threshold idea**

We do **not** model reserves vs. payments (that serves long-running P&C claims, not health reimbursement). Each line item resolves to a single `payable_amount`. We **do** adopt the threshold concept: line items the engine can fully decide are auto-adjudicated; ambiguous ones route to `needs_review`. **Rationale:** reserves are out of scope and add no value; the auto-adjudication-vs-human-review split is the realistic and demoable part worth keeping.

### Decision 10 — Sensitive health data → **Documented, not implemented: name the fields, tag them, describe the controls**

We do not build encryption or access control (out of scope). We **do** explicitly identify sensitive fields (member name, diagnosis code, provider details) in the schema with a `sensitive: true` marker/comment, and document in `decisions.md` that in production these would be column-encrypted and gated behind reader-roles (ServiceNow's `field encryption` + per-field reader/writer ACL pattern). **Rationale:** the assignment says design decisions should *reflect* data sensitivity; reflecting it precisely beats implementing it broadly within scope limits.

### Decision 11 — Participants → **Participant separated from Participant-Role; enables family floater**

A `Member` (person) is separate from their **role on a given policy/claim**. A policy can have multiple insured members (family floater) sharing one Sum Insured. **Rationale:** ServiceNow's who-vs-role split; cleanly enables the family-floater shared-pool case, which is a distinctive Indian-health modeling point.

### Decision 12 — Interface → **Next.js frontend + FastAPI REST backend; a real web app**

Full web application. REST API in Python/FastAPI, frontend in Next.js. **Rationale:** chosen by the team; gives a proper demonstrable product and clean API boundary.

### Summary of simplifications vs. ServiceNow

- Single line of business, not a generic multi-LOB framework (Decision 1).
- 3-level coverage model, not 4 (Decision 3).
- Single payable amount, no reserves/payments (Decision 9).
- Data sensitivity documented, not enforced (Decision 10).
- No fraud engine, no document OCR, no notifications, no auth.

### What we keep that's richer than a generic system

The Indian-specific adjudication rules: **Sum Insured**, **per-service Sub-limits** (esp. room rent), **Proportionate Deduction**, **Co-payment**, **Deductible**, **Waiting periods**, and **Exclusions**. These make the adjudication pipeline interesting and the explanations meaningful.

---

## 3. Domain model

### 3.1 Entity overview

```
CoveragePlan (template)
  └── CoverageType[]        (hospitalization, room_rent, pharmacy, diagnostics, daycare, ...)

Policy (instance of a CoveragePlan)
  ├── PolicySnapshot[]      (frozen copy of plan terms, taken at claim creation)
  ├── PolicyMember[]        (links Members to this policy with a role: primary / dependent)
  └── usage counters        (sum-insured consumed, per-sub-limit consumed, deductible met)

Member (person)            sensitive: name
  └── PolicyMember[]

Claim
  ├── policy_snapshot_id    (adjudicated against THIS, not the live policy)
  ├── member_id             (which insured member the claim is for)
  ├── stage + status        (two-axis claim state — see 3.4)
  ├── LineItem[]
  ├── DecisionLog[]         (append-only reasons at claim level)
  └── Dispute[]

LineItem
  ├── coverage_type_id      (what kind of expense this is)
  ├── billed_amount
  ├── diagnosis_code        sensitive
  ├── provider_name         sensitive
  ├── status                (line-item state — see 3.4)
  ├── payable_amount        (computed by the engine)
  └── Reason[]              (per-line-item explanation, the deduction breakdown)

Dispute
  ├── line_item_id (or claim_id)
  ├── state                 (raised / under_review / upheld / overturned)
  └── resolution notes
```

### 3.2 Entity definitions

**CoveragePlan** — a reusable product template.
- `id`, `name` (e.g. "Health Secure 5L"), `description`
- `sum_insured` (total annual coverage cap for the policy year)
- `deductible` (amount member bears before payouts begin; 0 if none)
- `copay_percent` (flat % member always bears; 0 if none)
- has many `CoverageType`

**CoverageType** — one category of covered expense, with its rules. This is where the configurable rule attributes live.
- `id`, `plan_id`, `code` (e.g. `room_rent`, `surgery`, `pharmacy`, `diagnostics`, `daycare`, `consultation`)
- `name`, `covered` (bool — false = excluded category)
- `sub_limit_type` (`none` | `absolute` | `percent_of_si`) — how the per-category cap is expressed
- `sub_limit_value` (e.g. 5000 absolute per day, or 1 meaning 1% of Sum Insured)
- `sub_limit_basis` (`per_day` | `per_claim` | `per_year`)
- `waiting_period_days` (0 if none; claim before this many days from policy start → denied)
- `triggers_proportionate_deduction` (bool — true for room_rent; when this category exceeds its sub-limit, associated charges scale)
- `subject_to_proportionate_deduction` (bool — true for surgery/OT/etc.; false for pharmacy/implants/diagnostics per IRDAI 2024)

**Policy** — an instance of a plan for a customer/family.
- `id`, `policy_number`, `plan_id`
- `start_date`, `end_date`, `status` (`in_force` | `lapsed`)
- usage counters (live, mutated as claims are paid): `sum_insured_consumed`, `deductible_consumed`, plus a per-CoverageType consumed map (see 3.3)

**PolicySnapshot** — frozen copy of the plan + policy terms + the usage counters *as of the moment the claim was created*. The claim stores `policy_snapshot_id` and the engine reads everything from here.
- Contains a denormalized copy of: sum_insured, deductible, copay_percent, full list of coverage-type rules, and the usage counters at snapshot time.

**Member** — an insured person. `id`, `name` (sensitive), `dob`.

**PolicyMember** — links a Member to a Policy. `policy_id`, `member_id`, `role` (`primary` | `dependent`). Multiple rows = family floater sharing one Sum Insured.

**Claim** — the container. Fields in 3.4.

**LineItem** — the adjudication unit. Fields in 3.1; status machine in 3.4.

**Reason** — a structured explanation fragment. `code` (machine), `message` (human), `amount_delta` (how much this step reduced the payable, if any), `step` (which pipeline stage emitted it).

**DecisionLog** — append-only claim-level event (`timestamp`, `actor` system/user, `message`). The audit/activity stream.

**Dispute** — `id`, `line_item_id` (nullable) or `claim_id`, `reason_text`, `state`, `resolution_text`, timestamps.

### 3.3 Usage tracking (the stateful-across-time part)

Claims are stateful across time: claim #3 cannot be adjudicated without knowing #1 and #2 already consumed part of the Sum Insured / sub-limits. Track, **per policy per policy-year**:

- `sum_insured_consumed` — running total paid against the policy.
- `deductible_consumed` — how much of the deductible the member has already absorbed.
- `sub_limit_consumed[coverage_type_code]` — running total paid per category (for `per_year` sub-limits).

When a claim is **paid** (reaches a terminal payable state), increment these counters. Because adjudication runs against a **snapshot**, take the snapshot of counters at claim creation — but apply increments to the live policy on settlement. (For the demo, simplest correct behavior: snapshot at creation, settle sequentially.)

### 3.4 The two state machines

These are deliberately separate. Build them as explicit enums + a transition function; do not scatter status strings.

#### Line-item state machine (the unit that actually gets adjudicated)

States:
- `submitted` — initial.
- `under_review` — engine ran but routed it to a human (ambiguous / needs info).
- `approved` — fully covered, payable computed = expected.
- `partially_approved` — covered but reduced (sub-limit cap, proportionate deduction, copay, allowed-amount).
- `denied` — not covered (exclusion, waiting period, limit exhausted).
- `paid` — terminal; payable amount disbursed; usage counters incremented.
- `disputed` — member contested; links to a Dispute.

Transitions:
```
submitted ──(engine: clear decision)──> approved | partially_approved | denied
submitted ──(engine: ambiguous)──────> under_review
under_review ──(human resolves)──────> approved | partially_approved | denied
approved | partially_approved ───────> paid
approved | partially_approved | denied ──(member contests)──> disputed
disputed ──(upheld)──> (returns to prior decision)
disputed ──(overturned)──> approved | partially_approved (re-adjudicate)
```

#### Claim state machine — two axes

**Stage** (coarse lifecycle position):
`submitted → under_adjudication → decided → settled → closed`
(plus `disputed` as a side-state that can re-open `decided`).

**Status** (the decision outcome, DERIVED from line items once adjudication completes):
- `approved` — all line items approved.
- `partially_approved` — mix of approved/partially_approved/denied, none needing review.
- `denied` — all line items denied.
- `needs_review` — at least one line item is `under_review` (claim cannot finalize until resolved).

**Derivation rule (implement exactly):**
```
if any line item is under_review        -> claim.status = needs_review, stage = under_adjudication
elif all line items denied              -> claim.status = denied,       stage = decided
elif all line items approved (full)     -> claim.status = approved,     stage = decided
else                                    -> claim.status = partially_approved, stage = decided
```
When all decided line items are paid → `stage = settled`. A dispute on any line item sets a `disputed` flag and can move the claim back toward `under_adjudication` for that item.

This derivation is the answer to "5 line items, 3 covered, 1 denied, 1 needs review": the claim sits at `needs_review` / `under_adjudication` until the 1 review item is resolved by a human, then re-derives to `partially_approved` / `decided`.

---

## 4. The adjudication engine (the heart of the system)

This is what the assignment is really evaluating. Build it as a **pure, deterministic, well-tested module** independent of the web layer. Given a line item + a policy snapshot + current usage counters, it returns a decision + a list of structured reasons. No DB calls inside the engine — pass everything in, get a result out. This makes it unit-testable and is the cleanest demonstration of the domain logic.

### 4.1 Rule representation (Decision 2 — decision-table-as-data)

Rules are **data**, evaluated by the pipeline. Two layers:

**(a) Coverage-type rules** live on each `CoverageType` (sub_limit, waiting_period, covered flag, proportionate-deduction flags) — already in the model. These are the per-category configurable rows.

**(b) The pipeline order** is a fixed, ordered list of rule *steps*. Each step is a small function with the signature:

```python
def step(ctx: AdjudicationContext) -> StepResult:
    # reads ctx (line item, snapshot, running payable, usage)
    # returns: possibly-reduced payable, zero or more Reasons,
    #          and optionally a terminal decision (denied / needs_review)
```

The engine runs steps in order, threading a running `payable` amount that starts at `billed_amount` and gets reduced. Any step may **short-circuit** to a terminal decision (e.g. exclusion → denied immediately). Each step that changes the outcome appends a `Reason`.

This is the decision-table pattern: the *what* (per-category limits) is data; the *how/order* (the pipeline) is a fixed, inspectable sequence. To add a rule you add a row or a step — you never edit a tangle of conditionals.

### 4.2 The adjudication pipeline (ordered steps)

Run per line item, in this exact order. `payable` starts at `billed_amount`.

1. **Coverage check.** Look up the line item's `CoverageType` in the snapshot. If not found or `covered == false` → **DENIED**. Reason: `EXCLUDED` — "Service type '{x}' is not covered under this policy." Short-circuit.

2. **Waiting-period check.** If `claim.service_date - policy.start_date < coverage_type.waiting_period_days` → **DENIED**. Reason: `WAITING_PERIOD` — "This service has a {n}-day waiting period; the policy was active only {m} days at the time of service." Short-circuit.

3. **Sub-limit cap.** If the coverage type has a sub-limit, compute the cap:
   - `absolute` → `sub_limit_value` (× days if `per_day` and the line item spans days).
   - `percent_of_si` → `sub_limit_value/100 × sum_insured`.
   If `payable > cap`: record the *excess*, set `payable = cap`, and **flag this line item as having breached its sub-limit** (needed for proportionate deduction). Reason: `SUB_LIMIT` — "Room rent is capped at ₹{cap}/day; billed ₹{billed}; ₹{excess} exceeds the sub-limit." Outcome becomes at most `partially_approved`.

4. **Proportionate deduction.** This is cross-line-item, so it runs in a **claim-level second pass** (see 4.3), not in the per-line-item pass. Placeholder here: mark the line item's ratio if it triggers deduction.

5. **Per-year limit / Sum-Insured-balance check.** If `sub_limit_consumed[code] + payable > sub_limit_value` (for `per_year` sub-limits) reduce `payable` to the remaining balance; if remaining is 0 → DENIED with `SUB_LIMIT_EXHAUSTED`. Similarly if `sum_insured_consumed + payable > sum_insured`, reduce to remaining Sum Insured; if 0 → DENIED with `SUM_INSURED_EXHAUSTED`. Reason records the reduction. Outcome at most `partially_approved`.

6. **Deductible.** If policy has a deductible not yet met: absorb `min(payable, deductible_remaining)` into the member's share, reduce `payable` accordingly, increment a working `deductible_consumed`. Reason: `DEDUCTIBLE` — "₹{x} applied toward the annual deductible." (Apply deductible once per claim across line items — see 4.3 ordering note.)

7. **Co-payment.** If `copay_percent > 0`: member bears `copay_percent%` of the remaining payable; reduce `payable` by that amount. Reason: `COPAY` — "{p}% co-payment (₹{x}) is borne by the member." Outcome at most `partially_approved`.

8. **Needs-review triggers.** Certain conditions can't be auto-decided → set **NEEDS_REVIEW** instead of finalizing (Decision 9, auto-vs-human split). Implement at least one realistic trigger, e.g.:
   - `billed_amount` above a configurable high-value threshold (e.g. ₹100,000) → route to human.
   - diagnosis/procedure mismatch flag (if you model it) → review.
   Reason: `NEEDS_REVIEW` — "Routed for manual review: {trigger}." Outcome `under_review`.

9. **Finalize.** If not short-circuited and not routed to review:
   - `payable == billed_amount` → `approved`.
   - `0 < payable < billed_amount` → `partially_approved`.
   - `payable == 0` → `denied` (with the accumulated reasons explaining why it reached 0).

### 4.3 Claim-level orchestration

The engine has an outer function that adjudicates the **whole claim**:

1. **First pass:** run the per-line-item pipeline for every line item (steps 1–3, 5–9), collecting per-item payable + reasons + the sub-limit-breach ratio.
2. **Proportionate-deduction pass (Indian-specific, step 4):** if any line item that `triggers_proportionate_deduction` (room_rent) breached its sub-limit, compute `ratio = cap / billed_room_rent`. For every *other* line item that is `subject_to_proportionate_deduction` (surgery, OT, consultation — but NOT pharmacy, implants, diagnostics per IRDAI 2024), multiply its current payable by `ratio`. Append Reason `PROPORTIONATE_DEDUCTION` — "Room rent exceeded its sub-limit (ratio {ratio}); associated charges reduced proportionately." Re-derive those items to `partially_approved`.
3. **Deductible ordering:** apply the policy deductible once, across the claim, against the summed payable (simplest: apply during line-item pass to the first line items until exhausted, OR apply as a claim-level step after the proportionate pass — pick one and document it; claim-level-after is cleaner and easier to explain).
4. **Derive claim stage + status** from the final set of line-item states (Section 3.4 rule).
5. **Write the DecisionLog** entries and persist payable amounts + reasons.

### 4.4 Worked example (use this as a test case)

Policy: Sum Insured ₹500,000; room-rent sub-limit 1% of SI = ₹5,000/day; co-pay 10%; no deductible. Claim, 1-day hospitalization:

| Line item | Coverage type | Billed |
|---|---|---|
| Room charges | room_rent | ₹8,000 |
| Surgeon fee | surgery | ₹40,000 |
| Medicines | pharmacy | ₹6,000 |
| MRI scan | diagnostics | ₹10,000 |

Adjudication:
- Room: sub-limit cap ₹5,000 → payable 5,000, excess 3,000, **breached**. Ratio = 5000/8000 = 0.625.
- Surgery: subject to proportionate deduction → 40,000 × 0.625 = 25,000.
- Pharmacy: NOT subject (IRDAI 2024) → stays 6,000.
- Diagnostics: NOT subject → stays 10,000.
- Subtotal after proportionate pass: 5,000 + 25,000 + 6,000 + 10,000 = 46,000.
- Co-pay 10%: member bears 4,600 → claim payable = 41,400.
- Claim status: `partially_approved` (room & surgery reduced). Stage: `decided`.

Every reduction has a Reason, so the member sees exactly why ₹64,000 billed became ₹41,400 payable. This worked example must be reproducible by a unit test.

---

## 5. API design (FastAPI, REST)

Base path `/api`. JSON in/out. No auth (out of scope). Use Pydantic models for every request/response. Return proper HTTP codes (200/201/400/404/409/422).

### 5.1 Reference data (seeded; read-only for the demo)

- `GET /api/plans` — list coverage plans with their coverage types.
- `GET /api/plans/{plan_id}` — one plan + coverage-type rules.
- `GET /api/policies` — list policies (with plan, members, usage counters).
- `GET /api/policies/{policy_id}` — one policy, including current usage counters and members.
- `GET /api/members` — list members (sensitive fields flagged in response meta, not hidden for demo).

### 5.2 Claims — core flow

- `POST /api/claims` — **submit a claim.** Body: `{ policy_id, member_id, service_date, line_items: [{ coverage_type_code, billed_amount, diagnosis_code, provider_name, description }] }`.
  - On submit: create the claim, **take the policy snapshot**, persist line items in `submitted`, then **run the adjudication engine**, persist results (payable + reasons per line item), derive claim stage/status, write DecisionLog. Return the fully adjudicated claim (201).
- `GET /api/claims` — list claims (filter by `status`, `stage`, `policy_id`).
- `GET /api/claims/{claim_id}` — full claim: line items, each line item's payable + ordered reasons, claim stage/status, decision log, policy snapshot reference, computed totals (total billed, total payable, total member-borne).
- `GET /api/claims/{claim_id}/explanation` — the EOB view: a structured, human-readable breakdown per line item (billed → each deduction step with amount and message → payable) plus claim totals. This is the "explain why" deliverable.

### 5.3 Adjudication control (internal/adjuster actions)

- `POST /api/claims/{claim_id}/line-items/{line_item_id}/resolve-review` — human resolves an `under_review` line item. Body: `{ decision: "approve" | "partially_approve" | "deny", payable_amount?, note }`. Updates the line item, re-derives claim status, logs the decision.
- `POST /api/claims/{claim_id}/settle` — move all approved/partially_approved line items to `paid`, **increment policy usage counters** (sum_insured_consumed, sub_limit_consumed, deductible_consumed), set claim stage `settled`. Guard: cannot settle while any line item is `under_review` (409).
- `POST /api/claims/{claim_id}/readjudicate` — re-run the engine (e.g. after dispute overturn or policy correction). Useful for demo.

### 5.4 Disputes

- `POST /api/claims/{claim_id}/disputes` — raise a dispute. Body: `{ line_item_id?, reason_text }`. Sets the line item (or claim) `disputed`, creates Dispute in `raised`, logs it.
- `GET /api/claims/{claim_id}/disputes` — list disputes for a claim.
- `POST /api/disputes/{dispute_id}/resolve` — resolve. Body: `{ outcome: "upheld" | "overturned", resolution_text, new_payable_amount? }`. `upheld` → original decision stands; `overturned` → line item moves to approved/partially_approved (optionally re-adjudicate), claim re-derives, logs it.

### 5.5 Response shape conventions

- Money as integers in paise OR decimals in rupees — **pick one and be consistent** (recommend decimal rupees with 2 dp, documented).
- Every line item response includes `reasons: [{ code, message, amount_delta, step }]` in pipeline order.
- Claim response always includes derived `stage`, `status`, and `totals`.
- Errors: `{ error: { code, message } }`.

---

## 6. Data layer

### 6.1 Storage

Use **PostgreSQL** (or SQLite for zero-setup local dev — recommend SQLite for the take-home so it "runs locally" trivially, with SQLAlchemy so it's swappable). ORM: SQLAlchemy + Alembic (or SQLModel). Seed via a script.

### 6.2 Tables (mirror Section 3)

`coverage_plans`, `coverage_types`, `policies`, `policy_members`, `members`, `policy_snapshots`, `claims`, `line_items`, `reasons`, `decision_logs`, `disputes`.

Notes:
- `policy_snapshots` stores a JSON blob of the frozen plan + coverage rules + usage counters at snapshot time. The claim FK-references the snapshot. The engine reads the snapshot JSON, never the live plan.
- `reasons` FK to `line_items` (and optionally `claims` for claim-level reasons like claim-level deductible/copay).
- Mark sensitive columns with a comment/metadata: `members.name`, `line_items.diagnosis_code`, `line_items.provider_name` → `-- SENSITIVE: column-encrypt + reader-role gate in production` (Decision 10).
- Usage counters on `policies`: `sum_insured_consumed`, `deductible_consumed`, and a `sub_limit_consumed` JSON map keyed by coverage_type_code.

### 6.3 Money & dates

- Money: `Decimal` in rupees, 2 dp. Never floats.
- Dates: ISO 8601. `service_date` on the claim drives waiting-period and snapshot logic.

---

## 7. Frontend (Next.js)

Keep it focused — the UI exists to **demonstrate** the engine, not to be a product. App Router, TypeScript, a component library is optional (Tailwind is fine). All data via the FastAPI REST API.

### 7.1 Pages

1. **`/` — Dashboard / claims list.** Table of claims: id, member, policy, total billed, total payable, **status badge** (color-coded: approved=green, partially=amber, denied=red, needs_review=blue), stage. Button: "New claim."

2. **`/claims/new` — Submit a claim.** Pick policy → pick member (filtered to that policy's members) → set service date → add line items (coverage type dropdown from the plan, billed amount, diagnosis code, provider, description). Submit → POST → redirect to the claim detail showing the adjudication result immediately.

3. **`/claims/[id]` — Claim detail (the money shot).** This page must make the adjudication legible:
   - Header: claim status + stage, totals (billed / payable / member-borne).
   - **Line-item breakdown table:** each line item as an expandable row showing the **waterfall of reasons** — billed amount at top, each deduction step (sub-limit, proportionate, copay, etc.) as a line with its `amount_delta` and human message, payable at the bottom. This *is* the explanation/EOB.
   - Per-line-item status badges.
   - For `under_review` items: an adjuster panel with approve / partially-approve / deny + note (calls resolve-review).
   - "Settle claim" button (disabled if anything needs review).
   - "Raise dispute" affordance per line item.
   - Decision log / activity stream at the bottom (timestamps + messages).

4. **`/claims/[id]/explanation` — printable EOB view** (optional but high-value): clean, member-facing rendering of `GET .../explanation`.

5. **`/policies` and `/policies/[id]`** — show policy terms, coverage-type rules, and **live usage counters** (Sum Insured consumed vs. remaining, sub-limit usage). Lets you demo limit exhaustion across multiple claims.

### 7.2 UX priorities

- The reason-waterfall on the claim detail page is the most important UI element — invest there. A reviewer should look at one line item and instantly understand *why* ₹8,000 became ₹5,000.
- Color-code statuses consistently.
- Show the policy snapshot reference on the claim so it's clear adjudication used frozen terms.

### 7.3 Design system

Read `/mnt/skills/public/frontend-design/SKILL.md` conventions before building UI. Keep it clean, legible, data-dense where useful (tables), uncluttered. Avoid generic dashboard kitsch; prioritize clarity of the adjudication breakdown.

---

## 8. Build sequence (so it's demoable at each step)

Build in this order. Each milestone produces something runnable.

1. **Domain + engine, pure Python, no web.** Implement entities as dataclasses/Pydantic, the adjudication pipeline, and the claim orchestration. Write unit tests including the Section 4.4 worked example and one test per pipeline step (exclusion, waiting period, sub-limit, proportionate deduction, sum-insured exhaustion, deductible, copay, needs-review, full approval, partial, denial). **This is the core deliverable — get it right and tested first.**
2. **Persistence.** SQLAlchemy models, migrations, seed script with the Section 9 scenarios.
3. **API.** FastAPI endpoints (Section 5) wrapping the engine + persistence. Test the submit→adjudicate→detail flow with curl/httpie.
4. **Settlement + usage counters.** Implement settle, counter increments, and verify limit-exhaustion across sequential claims.
5. **Disputes.** Raise + resolve, re-derivation.
6. **Frontend.** Claims list → new claim → claim detail (reason waterfall) → policy usage → disputes. In that order.
7. **Polish + docs.** Fill in the assignment deliverable docs (domain-model.md, decisions.md, self-review.md, README.md) from this spec.

### 8.1 Testing strategy

- **Engine unit tests** are mandatory and are where most test value lives — pure functions, deterministic, one test per rule + the composite worked example.
- **API integration tests** for submit/adjudicate/settle/dispute happy paths + key guards (can't settle with review pending).
- Keep the engine free of DB/HTTP so it stays trivially testable.

---

## 9. Seed scenarios (make the demo tell a story)

Seed at least these so every interesting behavior is demonstrable without manual setup:

1. **Clean full approval** — small claim, all line items within limits, no copay → `approved`. Shows the happy path.
2. **Room-rent + proportionate deduction** — the Section 4.4 example → `partially_approved`. The flagship demo.
3. **Exclusion** — a line item for a non-covered service (e.g. cosmetic) → that item `denied`, claim `partially_approved`. Shows category exclusion.
4. **Waiting period** — claim with `service_date` within a coverage type's waiting period → `denied` for that item. Shows time-based denial.
5. **Sum-Insured / sub-limit exhaustion across claims** — seed a policy with prior consumed usage so a new claim hits the remaining balance and is reduced or denied. Shows stateful-across-time tracking.
6. **Needs-review** — a high-value line item above the review threshold → `under_review`, claim `needs_review`; then demonstrate the adjuster resolving it. Shows the auto-vs-human split and the derived-claim-state mechanic ("3 covered, 1 denied, 1 needs review").
7. **Family floater** — a policy with a primary + dependent sharing one Sum Insured; claims by both draw down the same pool. Shows the participant/role model.
8. **Dispute** — a denied line item disputed and then overturned, re-adjudicated. Shows the dispute loop.

---

## 10. Mapping to assignment deliverables

When writing the required docs, source them from this spec:

- `docs/domain-model.md` ← Sections 3 (entities, relationships) + 3.4 (the two state machines, with diagrams).
- `docs/decisions.md` ← Section 2 (every decision, the ServiceNow reference, the simplification rationale) + the simplifications/keeps summary.
- `docs/self-review.md` ← honest notes: engine is well-tested and is the strength; settlement counter concurrency is simplified (sequential only); deductible-ordering choice documented; auth/encryption documented-not-implemented; proportionate-deduction is the most domain-accurate piece; needs-review trigger is a simple threshold, not real ML.
- `README.md` ← setup (SQLite + FastAPI + Next.js run instructions), seed command, how to walk the 8 scenarios.
- `ai-artifacts/` ← capture the coding-agent JSONL session logs from the start (mandatory for review).

---

## 11. Glossary (Indian health insurance terms)

- **Sum Insured** — total annual coverage cap for the policy (the ceiling for everything).
- **Sub-limit** — a cap on a specific category (e.g. room rent capped at 1% of Sum Insured per day).
- **Proportionate Deduction** — Indian rule: when room rent exceeds its sub-limit, *associated* charges (surgery, OT, consultation) are scaled down by the same ratio. Per IRDAI 2024, pharmacy, implants, diagnostics, and medical devices are **excluded** from this scaling.
- **Co-payment (Co-pay)** — a fixed percentage of the payable the member always bears.
- **Deductible** — an amount the member bears before the insurer pays anything (per year).
- **Waiting Period** — a period from policy start during which specified treatments aren't covered.
- **Exclusion** — a service category never covered.
- **Policy Snapshot** — a frozen copy of policy terms taken at claim creation, used for adjudication so later policy edits don't affect past claims.
- **Adjudication** — the per-line-item process of deciding coverage and computing the payable amount.
- **EOB (Explanation of Benefits)** — the breakdown shown to the member explaining billed → deductions → payable; here, the accumulated Reasons.
- **Reimbursement claim** — member pays the provider first, then claims the money back (the flow we model), vs. cashless/pre-authorization.
- **Family Floater** — a policy where multiple members share one Sum Insured pool.

---

*End of build specification.*

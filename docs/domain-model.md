# Domain Model

Indian health-insurance **reimbursement** claims: a member pays a provider, then claims
the money back. All adjudication happens after submission — there is no real-time hospital
round-trip to model.

This document describes the domain model — the entities, the two state machines, and where
each lives in the code.

---

## 1. Entities and relationships

```
CoveragePlan (reusable product template)
  └── CoverageType[]        hospitalization, room_rent, surgery, pharmacy, diagnostics,
                            consultation, daycare, maternity, cosmetic, dental, implants, ot
                            (each row carries its own rules — the decision table)

Policy (an instance of a CoveragePlan for a customer/family)
  ├── PolicyMember[]        Member ↔ Policy + role (primary | dependent)  → family floater
  ├── usage counters        sum_insured_consumed, deductible_consumed,
  │                         sub_limit_consumed{code → amount}   (mutated on settlement)
  └── PolicySnapshot[]      frozen copy of plan terms + counters, taken at claim creation

Member (a person)           name (SENSITIVE)

Claim
  ├── policy_snapshot_id     adjudicated against THIS, never the live policy
  ├── member_id              which insured member the claim is for
  ├── stage + status         two-axis claim state (see §3)
  ├── LineItem[]
  ├── DecisionLog[]          append-only activity stream
  └── Dispute[]

LineItem (the unit that gets adjudicated)
  ├── coverage_type_code     what kind of expense
  ├── billed_amount / payable_amount
  ├── diagnosis_code, provider_name   (SENSITIVE)
  ├── status                 line-item state machine
  └── Reason[]               ordered EOB / deduction waterfall

Dispute
  ├── line_item_id (nullable) | claim-level
  ├── state                  raised → under_review → upheld | overturned
  └── prior_status           the decision before the dispute, so "upheld" restores it
```

Code: pure domain DTOs in `app/backend/claims/domain/models.py`; ORM tables in
`app/backend/claims/persistence/models.py` — tables `coverage_plans`,
`coverage_types`, `policies`, `policy_members`, `members`, `policy_snapshots`, `claims`,
`line_items`, `reasons`, `decision_logs`, `disputes`.

### Sensitive data (documented, not enforced)
`members.name`, `line_items.diagnosis_code`, `line_items.provider_name` are tagged
`# SENSITIVE: encrypt + reader-role ACL` in the ORM. In production these would be
column-encrypted and gated behind a reader-role ACL; auth/encryption are out of scope here.

---

## 2. Coverage rules as data (the decision table)

Rules are **data evaluated by an engine**, not hardcoded `if/else` and not a full DSL. Two
layers:

1. **Per-category rules are rows.** Each `CoverageType` carries `covered`, `sub_limit_type`
   (`none | absolute | percent_of_si`), `sub_limit_value`, `sub_limit_basis`
   (`per_day | per_claim | per_year`), `waiting_period_days`,
   `triggers_proportionate_deduction`, `subject_to_proportionate_deduction`.
2. **The pipeline is a fixed, ordered list of steps**, each a small pure function
   `step(ctx) -> StepResult` (`app/backend/claims/engine/steps.py`). A running `payable`
   starts at `billed_amount` and is threaded through; any step may short-circuit to a
   terminal decision, and every step that changes the outcome appends a `Reason`.

To add a rule you add a row or a step — you never edit a tangle of conditionals.

The accumulated `Reason[]` per line item **is** the Explanation of Benefits — explanations
are a byproduct of how adjudication runs, not bolted on afterwards.

---

## 3. The two state machines

Built as explicit enums + a transition function (`app/backend/claims/domain/state_machine.py`).
Status is never a bare string.

### 3.1 Line item — its own machine

```
submitted ──engine: clear decision──▶ approved | partially_approved | denied
submitted ──engine: high value──────▶ under_review
under_review ──adjuster resolves────▶ approved | partially_approved | denied
approved | partially_approved ──────▶ paid
approved | partially_approved | denied ──member contests──▶ disputed
disputed ──overturned───────────────▶ approved | partially_approved
disputed ──upheld───────────────────▶ (prior decision restored, incl. denied)
```

- `paid` is terminal (no `disputed` edge) — settled lines aren't disputed in this build.
- `under_review` carries the engine's fully-computed, rules-capped payable; the adjuster
  may confirm or reduce it, never exceed it (see Decisions doc, "Needs-review").

### 3.2 Claim — two axes (stage + derived status)

**Stage** (coarse lifecycle): `submitted → under_adjudication → decided → settled → closed`.

**Status** is **DERIVED** from the line items, never set directly (`derive_claim_state`):

```
if any line item is under_review   → status = needs_review,        stage = under_adjudication
elif all line items denied         → status = denied,              stage = decided
elif all line items approved       → status = approved,            stage = decided
else                               → status = partially_approved,  stage = decided
```

On settlement, paid line items advance the claim to `stage = settled` (status unchanged).
A dispute re-opens the claim to `under_adjudication`; on resolution it re-derives.

This derivation is the answer to **"5 line items: 3 covered, 1 denied, 1 needs review"** —
the claim sits at `needs_review / under_adjudication` until the review is resolved, then
re-derives to `partially_approved / decided`. (Seeded as scenario 6.)

---

## 4. Policy snapshots

At claim creation, the policy terms + usage counters are frozen into a `PolicySnapshot`
(stored as pydantic JSON text so Decimals round-trip exactly —
`app/backend/claims/service/snapshot.py`). The engine adjudicates **only** against the
snapshot, so later edits to the live policy never change a past claim's outcome. Verified
by `test_snapshot_isolated_from_later_policy_edits`.

## 5. Usage tracking (stateful across time)

Live counters on `policies`: `sum_insured_consumed`, `deductible_consumed`, and a
`sub_limit_consumed` JSON map (per-year sub-limits only). Incremented **on settlement**,
not on adjudication. Because adjudication reads the snapshot taken at creation, the demo
settles sequentially (documented simplification — see self-review). This is what makes
the exhaustion scenario aware that prior settled claims already consumed most of the Sum
Insured. In the seed data, claim #5 demonstrates this with a policy that has only ₹2,000
remaining.

## 6. Money

`Decimal` rupees, quantized to 2 dp, everywhere (`app/backend/claims/domain/money.py`);
floats are refused at the boundary. Stored in SQLite as TEXT via a `Money` type decorator
(SQLAlchemy `Numeric` round-trips through float on SQLite). Serialized over the API as exact
2 dp decimal strings.

---
name: adjudication-engine
description: Gotchas and invariants for the claims adjudication engine — load when building or modifying the pipeline, line-item/claim adjudication, policy snapshots, usage counters, or reasons/EOB logic.
---

# Adjudication engine — quick reference

**SPEC.md §4 is authoritative.** So is `ServiceNowDocs/markdown/financial-services-operations/insurance-claims/update-insurance-claims-automation-using-decision-tables.md` for the decision-table pattern. This file is a gotcha checklist, not a re-statement — when in doubt, read SPEC §4.

## Invariants (get these wrong and the engine is wrong)

- **Pure & DB-free.** Signature: `(line_item, policy_snapshot, usage_counters) -> decision + ordered Reasons`. No DB or HTTP calls inside the engine. Everything is passed in. This is what makes it unit-testable — keep it that way.
- **Adjudicate against the snapshot, never the live policy** (Decision 7). Later policy edits must not change past claims.
- **Money is `Decimal`, rupees, 2 dp — never float.** Every amount, every ratio multiplication, every reason `amount_delta`.
- **Status only via enum + transition function** (SPEC §3.4) — never scatter status strings. Claim `status` is **derived** from line items (implement §3.4 derivation verbatim), not set directly.
- **Reasons are a byproduct.** Every step that changes the outcome appends a `Reason { code, message, amount_delta, step }` in pipeline order. The accumulated reasons *are* the EOB — don't build explanations separately.

## Pipeline order (SPEC §4.2) — `payable` starts at `billed_amount`

coverage check → waiting period → sub-limit cap → *(proportionate-deduction placeholder)* → per-year / sum-insured balance → deductible → co-payment → needs-review triggers → finalize.

Any step may short-circuit to a terminal decision (e.g. exclusion → DENIED immediately).

## Proportionate deduction — the easy thing to get wrong

- It is **cross-line-item**, so it runs in a **claim-level second pass** (§4.3), not in the per-line-item loop.
- Trigger: a `triggers_proportionate_deduction` item (room_rent) breaches its sub-limit → `ratio = cap / billed_room_rent`.
- Apply: scale the payable of every *other* `subject_to_proportionate_deduction` item by `ratio`.
- **IRDAI 2024 exclusions — NOT scaled:** pharmacy, implants, diagnostics. (Scaled: surgery, OT, consultation.) This is the most domain-accurate rule in the system; the seed flags drive it — don't hardcode the category list.

## Canonical test (mandatory)

The §4.4 worked example must be reproducible by a unit test: ₹64,000 billed → **₹41,400 payable** (room ₹8k→₹5k cap, ratio 0.625; surgery ₹40k→₹25k; pharmacy ₹6k stays; diagnostics ₹10k stays; subtotal ₹46k; 10% copay → ₹41,400; claim `partially_approved`, stage `decided`). Write one test per pipeline step in addition to this composite.

# Self-Review

My honest read on what's solid, what's thin, and what I'd do next.

## Reviewer summary

| Area | My read |
|------|---------|
| Core adjudication | Strong: pure engine, Decimal money, worked example, one test per rule step. |
| Explanation/EOB | Strong: reasons are emitted by the rule steps and rendered directly. |
| Lifecycle | Solid: line-item machine, derived claim status, settlement/dispute guards. |
| UI | Good demo coverage; intentionally simple, no automated E2E suite. |
| Production gaps | Known: settlement concurrency, auth/encryption, pagination, richer review logic. |

The main thing I would ask a reviewer to inspect is claim #2's waterfall and claim #6's
review flow. Those two screens show the hardest domain decisions.

## What I'm happy with

- **The adjudication engine.** It's a pure, deterministic module with no database or HTTP
  inside — you pass in a line item, the frozen policy terms, and the usage counters, and you
  get back a decision plus an ordered list of reasons. That made it easy to test hard: the
  ₹64,000 → ₹41,400 worked example, one test per pipeline step, and the tricky parts
  (proportionate deduction, sum-insured exhaustion across claims, the claim-status
  derivation). The tests check domain behaviour, not HTTP status codes.
- **Proportionate deduction** is the part I'm most confident is domain-correct. When room
  rent breaches its cap, the associated charges scale down by the same ratio — but pharmacy,
  diagnostics, and implants are excluded (IRDAI 2024). That exclusion is a flag on the data,
  not an `if` buried in the engine, so the rule is easy to change.
- **Explanations come for free.** Every reduction the engine makes records a reason with its
  amount. That same list is what the API returns and what the UI renders as the waterfall, so
  "why is the payable ₹4,500?" is always answerable and never reconstructed after the fact.
- **Snapshots actually isolate.** A claim is judged against a frozen copy of the policy, so
  editing the policy later can't change a past claim's outcome. There's a test that proves it.
- **Claim status is always derived from its line items**, never set by hand, and you can't
  settle a claim that still has a line under review or an open dispute.

## What's rough or deliberately left out

- **Settlement assumes one claim at a time.** Usage counters are frozen when a claim is
  created and only applied when it's settled. If you open two claims before settling either,
  both see the same headroom and could together overspend the sum insured. Doing it properly
  needs row locking or a re-check at settlement time; I left it as a documented simplification.
- **One ordering choice is genuinely debatable.** Where the overall sum-insured cap sits
  relative to proportionate deduction has two reasonable answers. I scale the associated
  charges first and apply the sum-insured ceiling last; someone could argue the reverse. It
  only matters when a room-rent breach and an exhausted sum insured land in the same claim,
  which I haven't tested in combination.
- **"Needs review" is just a rupee threshold**, not real fraud/triage logic — a stand-in for
  the auto-decide-vs-send-to-a-human split.
- **No auth, encryption, or access control.** The sensitive fields (member name, diagnosis,
  provider) are tagged in the schema with a note on how they'd be protected in production, but
  nothing is enforced — out of scope here.
- **No automated frontend tests.** I checked the UI by clicking through the running app and
  by the build/lint passing; the real test value is in the backend.
- **The claims list does an extra query per row** (member/policy lookups) and there's no
  pagination — fine for a seeded demo, not for real volume.

## Bugs I hit while building (and fixed)

- **The big one:** at first a high-value line was sent to manual review *before* its sub-limit
  cap was applied, and the reviewer could then approve the full billed amount — so room rent
  billed at ₹1,50,000 could be paid against a ₹5,000 cap. I moved the review step to run after
  all the automatic reductions, so a reviewer can only confirm or lower the rules-allowed
  amount, never exceed it. Added a regression test.
- A few smaller ones, each now covered by a test: reasons were briefly saved without their
  parent line item (the foreign key was set before the row was flushed); money columns
  defaulted to the string `"0"` and broke arithmetic on brand-new policies; a per-year
  sub-limit bucket was debited by the pre-cap amount; and a claim with an open dispute could
  still be settled.

## What I'd do with more time

1. Real concurrency safety at settlement (locking + a sum-insured re-check).
2. A test for the breach-plus-exhaustion ordering edge.
3. Eager-loading and pagination on the claims list.
4. A small end-to-end test for the main UI flows.
5. Settle the ordering question with whoever owns the rules, rather than picking for them.

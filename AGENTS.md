# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Current state

This is a **take-home assignment, pre-implementation.** The repo currently contains only specs:

- `SPEC.md` — the **authoritative build specification.** Read it top to bottom before writing any code. Every non-obvious design choice is settled there with rationale (Section 2). Do not re-litigate those decisions.
- `instructions/problem_statement.md` — the original problem brief (what the graders asked for).
- `instructions/candidate_assignment_instructions.md` — grading rubric and submission rules.

When `SPEC.md` and this file disagree, `SPEC.md` wins. This file summarizes; the spec is the source of truth.

## What is being built

A **Claims Processing System** for Indian health insurance **reimbursement** claims (member pays first, claims back later — so adjudication happens entirely post-submission, no real-time hospital round-trip).

Stack (Decision 12): **Next.js** (App Router, TypeScript) frontend + **Python/FastAPI** REST backend + **SQLite** via SQLAlchemy (swappable to Postgres). Money is `Decimal` rupees, 2dp — never floats.

## The architecture that matters

The system has one hard core and everything else wraps it.

### The adjudication engine (the heart — SPEC.md §4)

A **pure, deterministic, DB-free module.** Signature: `(line_item, policy_snapshot, usage_counters) -> decision + ordered Reasons`. No DB or HTTP calls inside the engine — pass everything in, get a result out. This is what makes it unit-testable, and it is the primary thing being evaluated.

Two layers of rule representation (Decision 2, decision-table-as-data):
- **Per-category rules are data** — sub-limits, waiting periods, `covered` flag, proportionate-deduction flags live as columns on `CoverageType` rows.
- **The pipeline is a fixed ordered list of steps**, each a small function `step(ctx) -> StepResult`. A running `payable` starts at `billed_amount` and is threaded through, reduced by each step. Any step may short-circuit to a terminal decision. Every step that changes the outcome appends a structured `Reason`. To add a rule you add a row or a step — never edit a tangle of `if/else`.

**Pipeline order (exact — SPEC.md §4.2):** coverage check → waiting period → sub-limit cap → (proportionate-deduction placeholder) → per-year / sum-insured balance → deductible → co-payment → needs-review triggers → finalize.

**Proportionate deduction is cross-line-item**, so it runs in a **claim-level second pass** (§4.3), not the per-line-item pass: if a `triggers_proportionate_deduction` item (room_rent) breaches its sub-limit, `ratio = cap / billed_room_rent`, and every *other* `subject_to_proportionate_deduction` item (surgery, OT, consultation — **NOT** pharmacy, implants, diagnostics, per IRDAI 2024) has its payable scaled by `ratio`. The §4.4 worked example (₹64,000 billed → ₹41,400 payable) **must be reproducible by a unit test.**

### Two separate state machines (Decision 4, SPEC.md §3.4)

Build them as explicit enums + a transition function; **do not scatter status strings.**

- **Line item** has its own machine: `submitted → approved | partially_approved | denied | under_review → paid | disputed`.
- **Claim** has two axes: a coarse `stage` (`submitted → under_adjudication → decided → settled → closed`) and a `status` that is **DERIVED from its line items**, not set directly. The derivation rule in §3.4 is exact — implement it verbatim. This derivation is the answer to the "3 covered, 1 denied, 1 needs review" problem and is a core thing being tested.

### Policy snapshots (Decision 7)

At claim creation, **freeze the policy terms + usage counters into a `PolicySnapshot`** (a JSON blob). The engine adjudicates against the snapshot, never the live policy — so later policy edits don't change past claims. The claim FK-references the snapshot.

### Usage counters (the stateful-across-time part, §3.3)

Live counters on `policies`: `sum_insured_consumed`, `deductible_consumed`, and a `sub_limit_consumed` JSON map keyed by coverage_type_code. Incremented **on settlement**, not on adjudication. Snapshot at creation, settle sequentially (concurrency is deliberately simplified — document this).

### Explanations are a byproduct, not bolted on (Decision 6)

Each pipeline step emits a `Reason { code, message, amount_delta, step }`. The accumulated reasons per line item *are* the EOB / deduction waterfall. The `GET /api/claims/{id}/explanation` endpoint and the claim-detail UI render this waterfall — it is the single most important UI element (SPEC.md §7.2).

## Build order (SPEC.md §8 — each milestone is runnable)

1. **Domain + engine, pure Python, no web.** Entities + pipeline + claim orchestration, with unit tests (the §4.4 worked example + one test per pipeline step). **Get this right and tested first** — it is the core deliverable.
2. Persistence (SQLAlchemy models, migrations, seed script).
3. API (FastAPI, SPEC.md §5).
4. Settlement + usage counters; verify limit exhaustion across sequential claims.
5. Disputes (raise + resolve + re-derivation).
6. Frontend (claims list → new claim → claim detail waterfall → policy usage → disputes).
7. Docs.

Tests must appear **before or alongside** implementation in git history (graders check this) and must encode domain rules, not just assert HTTP status codes. The engine is pure, deterministic, and is where most test value lives.

## Assignment constraints (these affect how you work, not just what you build)

- **Sensitive health fields** (`members.name`, `line_items.diagnosis_code`, `line_items.provider_name`) are **documented, not protected** (Decision 10): mark them `sensitive`/with a comment noting column-encryption + reader-role gating in production. Do not build auth, encryption, or access control — out of scope.
- **Out of scope (do not build):** auth/login, policy purchase, account management, notifications, dashboards, admin panels, multi-tenancy, RBAC, reserves/payments split, fraud scoring, OCR.
- **Required deliverables** (submission is rejected without any one): working system, `docs/domain-model.md`, `docs/decisions.md`, `docs/self-review.md`, `README.md`, `.git/` history, and `ai-artifacts/` containing **raw `.jsonl` agent session logs covering every phase**. The doc-to-spec mapping is in SPEC.md §10.
- Self-review must be **honest and match reality** — name what's thin or skipped with the trade-off. SPEC.md §10 lists the known soft spots to disclose.

## Working agreement (how to build, not just what)

Aditya reads and approves every line. Write code to be read and approved, not just to run.

**Think before coding.** Reason through the whole feature first, including edge cases skipped while explaining. If you spot a gap, an unhandled case, or multiple interpretations, stop and ask before implementing — don't silently pick one.

**Production-grade by default.** Correct, observable, and handling the cases that are real. Long-horizon work, not demos: take the correct path, never fast-but-throwaway. Within that, write the minimum code that solves the problem — no speculative abstractions, config, fallbacks, or error handling not asked for or not a real case. If something fails, surface the failure — don't swallow it. When a feature is updated it changes; don't preserve old behavior "just in case" unless asked. Surface behavior at boundaries and state changes.

**Bugs: reproduce first.** When a bug is reported, reproduce it (a failing test), then fix it, then clean up. Don't refactor unrelated code unless it materially improves correctness or clarity.

**Goal-driven execution.** Turn the task into a verifiable goal and a brief plan, then loop until it's *actually verified* — not "looks done."

### The loop: Explore → Plan → Code → Verify → Commit → Review

Run this per milestone (Build order above / SPEC §8). Use plan mode for any multi-file milestone; skip it for typo-scale edits.

- **Explore.** Delegate codebase research to the `Explore` subagent so it doesn't fill the main context.
- **Plan.** For a milestone, write the approach down before coding.
- **Code, test-first.** Engine unit tests appear **before or alongside** implementation in git history (graders check this) and must encode domain rules, not just HTTP status. One test per pipeline step; the §4.4 worked example (₹64k→₹41.4k) is a **mandatory** test. API: happy paths + guards (e.g. can't settle with a review pending).
- **Verify for real, not smoke tests.** A change isn't done until a check Codex can run passes. Engine: `pytest`. Frontend: verify by **clicking through the running app** with the `browser-e2e-verifier` agent and screenshotting the reason-waterfall — never assume "looks done." After Python edits, a non-blocking hook auto-runs `ruff format` + the nearest `pytest` and surfaces failures (visibility only; it never blocks). Show the evidence (test output, screenshot), don't just assert success.
- **Commit** — only when asked. Branch per milestone off `main` (`milestone/1-engine`, `milestone/2-persistence`, …). Conventional messages, ending with the `Co-Authored-By: Codex` trailer. One PR per milestone via `gh` when asked. Never commit/push unprompted.
- **Review.** Before treating a milestone done, run the `domain-code-reviewer` agent on the diff in fresh context (SPEC-rule gaps, not style). Built-in `/code-review` is the generic bug-hunt; the domain reviewer adds spec awareness. Fix gaps that affect correctness or stated requirements; don't chase style or over-engineer.

**ai-artifacts (mandatory deliverable).** `ai-artifacts/` must hold raw `.jsonl` agent session logs covering **every phase** — submission is rejected without it. Transcripts live at `~/.Codex/projects/-Users-adityapeela-Documents-projects-realfast_assignment/*.jsonl`; the README documents the copy command, run manually at the end of each phase. (Don't gitignore `ai-artifacts/`.)

## ServiceNow reference docs

The domain lineage (Decisions cite "ServiceNow") is in the local `ServiceNowDocs/` clone — consult `ServiceNowDocs/markdown/financial-services-operations/insurance-claims/` when modeling coverage rules, especially `update-insurance-claims-automation-using-decision-tables.md` (maps to Decision 2, decision-table-as-data). **SPEC's simplifications override ServiceNow's full genericity** (Decisions 1/3/9/10): single line of business, 3-level coverage model, single payable, documented-not-enforced sensitivity. `ServiceNowDocs/` is gitignored (local reference only).

## Commands

No build tooling exists yet — establish it during milestone 1/2/3. When you do, update this section with the real commands (backend run/test, single-test invocation, frontend dev/build, seed script, and the ai-artifacts copy command). Until then there is nothing to run.

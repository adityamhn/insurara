"""The two state machines, as explicit transition tables + a derivation
function. Status is changed only through here — never by assigning strings ad hoc.

- Line items have their own machine.
- A claim's `status` is DERIVED from its line items (not set directly); its `stage`
  follows from the same derivation. This derivation is the answer to the
  "3 covered, 1 denied, 1 needs review" problem.
"""

from __future__ import annotations

from .enums import ClaimStage, ClaimStatus, LineItemStatus

# Allowed line-item transitions. A target absent from a state's set is
# illegal. `paid` is terminal. `disputed` re-opens to a covered decision on overturn;
# an "upheld" dispute restores the prior decision, which the caller persists and
# replays rather than encoding as a generic edge.
_LINE_ITEM_TRANSITIONS: dict[LineItemStatus, frozenset[LineItemStatus]] = {
    LineItemStatus.SUBMITTED: frozenset(
        {
            LineItemStatus.APPROVED,
            LineItemStatus.PARTIALLY_APPROVED,
            LineItemStatus.DENIED,
            LineItemStatus.UNDER_REVIEW,
        }
    ),
    LineItemStatus.UNDER_REVIEW: frozenset(
        {
            LineItemStatus.APPROVED,
            LineItemStatus.PARTIALLY_APPROVED,
            LineItemStatus.DENIED,
        }
    ),
    LineItemStatus.APPROVED: frozenset({LineItemStatus.PAID, LineItemStatus.DISPUTED}),
    LineItemStatus.PARTIALLY_APPROVED: frozenset({LineItemStatus.PAID, LineItemStatus.DISPUTED}),
    LineItemStatus.DENIED: frozenset({LineItemStatus.DISPUTED}),
    LineItemStatus.PAID: frozenset(),
    # Overturn → a covered decision; uphold → restore the prior decision (which may
    # have been a denial), so DENIED is reachable too.
    LineItemStatus.DISPUTED: frozenset(
        {
            LineItemStatus.APPROVED,
            LineItemStatus.PARTIALLY_APPROVED,
            LineItemStatus.DENIED,
        }
    ),
}

# The adjudication-time outcomes derivation operates over.
_ADJUDICATED = frozenset(
    {
        LineItemStatus.APPROVED,
        LineItemStatus.PARTIALLY_APPROVED,
        LineItemStatus.DENIED,
        LineItemStatus.UNDER_REVIEW,
    }
)


class IllegalTransition(Exception):
    """Raised when a line-item state change violates the machine."""


def can_transition(current: LineItemStatus, target: LineItemStatus) -> bool:
    return target in _LINE_ITEM_TRANSITIONS[current]


def transition(current: LineItemStatus, target: LineItemStatus) -> LineItemStatus:
    """Validate and return the target state, or raise IllegalTransition."""
    if not can_transition(current, target):
        raise IllegalTransition(f"{current.value} -> {target.value} is not allowed")
    return target


def derive_claim_state(
    line_statuses: list[LineItemStatus],
) -> tuple[ClaimStatus, ClaimStage]:
    """Derive (status, stage) from line-item states — the exact rule:

        if any under_review   -> needs_review, under_adjudication
        elif all denied       -> denied,       decided
        elif all approved     -> approved,     decided
        else                  -> partially_approved, decided

    Operates on adjudication-time outcomes only. `paid`/`settled` is a settlement
    concern (stage transitions to `settled` once all decided items are paid) handled
    by the caller; this function deliberately rejects non-adjudicated states so the
    derivation can never silently misclassify.
    """
    if not line_statuses:
        raise ValueError("cannot derive claim state from zero line items")
    bad = [s for s in line_statuses if s not in _ADJUDICATED]
    if bad:
        raise ValueError(f"derive_claim_state expects adjudicated outcomes, got {bad[0].value}")

    if any(s is LineItemStatus.UNDER_REVIEW for s in line_statuses):
        return ClaimStatus.NEEDS_REVIEW, ClaimStage.UNDER_ADJUDICATION
    if all(s is LineItemStatus.DENIED for s in line_statuses):
        return ClaimStatus.DENIED, ClaimStage.DECIDED
    if all(s is LineItemStatus.APPROVED for s in line_statuses):
        return ClaimStatus.APPROVED, ClaimStage.DECIDED
    return ClaimStatus.PARTIALLY_APPROVED, ClaimStage.DECIDED

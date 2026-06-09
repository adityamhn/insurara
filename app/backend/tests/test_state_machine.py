"""The two state machines (SPEC §3.4): claim-state derivation and line-item transitions."""

import pytest

from claims.domain.enums import ClaimStage, ClaimStatus, LineItemStatus
from claims.domain.state_machine import (
    IllegalTransition,
    can_transition,
    derive_claim_state,
    transition,
)

A = LineItemStatus.APPROVED
PA = LineItemStatus.PARTIALLY_APPROVED
D = LineItemStatus.DENIED
UR = LineItemStatus.UNDER_REVIEW


# Derivation rule -------------------------------------------------------------
def test_all_approved_yields_approved_decided():
    assert derive_claim_state([A, A]) == (ClaimStatus.APPROVED, ClaimStage.DECIDED)


def test_all_denied_yields_denied_decided():
    assert derive_claim_state([D, D]) == (ClaimStatus.DENIED, ClaimStage.DECIDED)


def test_mix_without_review_is_partially_approved_decided():
    assert derive_claim_state([A, PA, D]) == (
        ClaimStatus.PARTIALLY_APPROVED,
        ClaimStage.DECIDED,
    )


def test_any_under_review_dominates_to_needs_review():
    # "3 covered, 1 denied, 1 needs review" -> claim waits in needs_review.
    assert derive_claim_state([A, A, A, D, UR]) == (
        ClaimStatus.NEEDS_REVIEW,
        ClaimStage.UNDER_ADJUDICATION,
    )


def test_derivation_rejects_non_adjudicated_states():
    with pytest.raises(ValueError):
        derive_claim_state([A, LineItemStatus.PAID])
    with pytest.raises(ValueError):
        derive_claim_state([])


# Line-item transitions -------------------------------------------------------
def test_legal_transitions():
    assert transition(LineItemStatus.SUBMITTED, UR) is UR
    assert transition(UR, PA) is PA
    assert transition(A, LineItemStatus.PAID) is LineItemStatus.PAID
    assert transition(D, LineItemStatus.DISPUTED) is LineItemStatus.DISPUTED


def test_illegal_transitions_raise():
    # Can't pay a denied line, can't move out of a terminal paid state.
    with pytest.raises(IllegalTransition):
        transition(D, LineItemStatus.PAID)
    with pytest.raises(IllegalTransition):
        transition(LineItemStatus.PAID, A)
    assert not can_transition(LineItemStatus.SUBMITTED, LineItemStatus.PAID)

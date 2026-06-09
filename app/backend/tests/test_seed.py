"""The seed must tell the SPEC §9 story: each scenario lands in its expected state."""

from collections import Counter
from decimal import Decimal

from claims.domain.enums import ClaimStatus, LineItemStatus
from claims.domain.money import rupee


def test_each_scenario_reaches_expected_claim_status(seeded):
    _, claims = seeded
    expected = {
        "clean_approval": ClaimStatus.APPROVED,
        "proportionate": ClaimStatus.PARTIALLY_APPROVED,
        "exclusion": ClaimStatus.PARTIALLY_APPROVED,
        "waiting_period": ClaimStatus.DENIED,
        "exhaustion": ClaimStatus.PARTIALLY_APPROVED,
        "needs_review": ClaimStatus.NEEDS_REVIEW,
        "family_floater": ClaimStatus.PARTIALLY_APPROVED,
    }
    for name, status in expected.items():
        assert claims[name].status is status, f"{name} expected {status}"


def test_needs_review_is_three_covered_one_denied_one_review(seeded):
    _, claims = seeded
    counts = Counter(li.status for li in claims["needs_review"].line_items)
    assert counts[LineItemStatus.PARTIALLY_APPROVED] == 3
    assert counts[LineItemStatus.DENIED] == 1
    assert counts[LineItemStatus.UNDER_REVIEW] == 1


def test_exhaustion_reduces_to_remaining_sum_insured(seeded):
    _, claims = seeded
    line = claims["exhaustion"].line_items[0]
    assert line.payable_amount == rupee("2000")  # ₹3,00,000 - ₹2,98,000 consumed
    assert line.status is LineItemStatus.PARTIALLY_APPROVED


def test_family_floater_two_members_share_one_policy(seeded):
    _, claims = seeded
    asha_claim = claims["proportionate"]
    rohan_claim = claims["family_floater"]
    assert asha_claim.policy_id == rohan_claim.policy_id
    assert asha_claim.member_id != rohan_claim.member_id


def test_clean_approval_emits_no_deductions(seeded):
    _, claims = seeded
    claim = claims["clean_approval"]
    assert all(li.status is LineItemStatus.APPROVED for li in claim.line_items)
    assert all(li.reasons == [] for li in claim.line_items)
    total = sum((li.payable_amount for li in claim.line_items), Decimal("0"))
    assert total == rupee("10000")

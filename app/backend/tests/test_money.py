"""Money invariant: Decimal rupees at 2dp, floats refused at the boundary."""

from decimal import Decimal

import pytest

from claims.domain.money import quantize, rupee


def test_rupee_quantizes_to_two_places():
    assert rupee("5") == Decimal("5.00")
    assert rupee(8000) == Decimal("8000.00")
    assert rupee(Decimal("41400")) == Decimal("41400.00")


def test_rupee_rounds_half_up():
    assert rupee("0.005") == Decimal("0.01")
    assert quantize(Decimal("2500.625")) == Decimal("2500.63")


def test_rupee_refuses_float():
    # Floats reintroduce binary rounding error; the boundary must reject them.
    with pytest.raises(TypeError):
        rupee(0.1)

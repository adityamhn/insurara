"""Money is Decimal rupees, quantized to 2 decimal places — never float.

Every amount, ratio multiplication, and reason `amount_delta` flows through these
helpers so rounding is applied consistently and the engine stays exact.
"""

from decimal import Decimal, ROUND_HALF_UP

# Two-decimal-place rupee quantum, e.g. Decimal("0.01").
_RUPEE_QUANTUM = Decimal("0.01")

# Convenience zero already at rupee precision.
ZERO = Decimal("0.00")


def rupee(value: object) -> Decimal:
    """Coerce a value into a 2dp Decimal rupee amount.

    Accepts int/str/Decimal. Floats are rejected — they reintroduce the binary
    rounding error this module exists to avoid; callers must pass int/str/Decimal.
    """
    if isinstance(value, float):
        raise TypeError(f"refusing to build money from float {value!r}; pass int, str, or Decimal")
    return Decimal(value).quantize(_RUPEE_QUANTUM, rounding=ROUND_HALF_UP)


def quantize(amount: Decimal) -> Decimal:
    """Round an already-Decimal amount to 2dp (used after ratio multiplications)."""
    return amount.quantize(_RUPEE_QUANTUM, rounding=ROUND_HALF_UP)

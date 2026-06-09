"""SQLAlchemy column types that preserve domain invariants.

SQLite has no exact decimal type, and SQLAlchemy's Numeric round-trips through float on
SQLite — which is exactly the precision loss `domain.money` exists to prevent. So money
is stored as TEXT (the canonical 2dp string) and reconstructed as a Decimal on load.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from ..domain.money import rupee


class Money(TypeDecorator):
    """Decimal rupees stored as a 2dp TEXT string; never float. Used for every money
    column and for percent columns (also exact at 2dp)."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value: Decimal | int | str | None, dialect) -> str | None:
        if value is None:
            return None
        return str(rupee(value))

    def process_result_value(self, value: str | None, dialect) -> Decimal | None:
        if value is None:
            return None
        return rupee(value)

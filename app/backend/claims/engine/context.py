"""Working state threaded through the adjudication pipeline.

`AdjudicationContext` holds everything one line item needs — all passed in, nothing
fetched (SPEC §4: pure & DB-free). The running `payable` starts at `billed_amount` and
is reduced by each step. `StepResult` is what a per-line step returns: the (possibly
reduced) payable, any Reasons it emitted, and an optional terminal decision that
short-circuits the rest of the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..domain.enums import LineItemStatus
from ..domain.models import (
    CoverageTypeRule,
    LineItemInput,
    PolicySnapshot,
    Reason,
    UsageCounters,
)


@dataclass
class AdjudicationContext:
    """Mutable per-line working state. One per line item."""

    line: LineItemInput
    rule: CoverageTypeRule | None  # resolved from the snapshot; None = unknown code
    snapshot: PolicySnapshot
    usage: UsageCounters
    service_date: date

    payable: Decimal  # running amount, starts at billed_amount
    reasons: list[Reason] = field(default_factory=list)

    # Outcome flags accumulated across steps.
    terminal_status: LineItemStatus | None = None  # set => short-circuit
    breached_sub_limit: bool = False
    proportionate_ratio: Decimal | None = None  # set if this line drives prop. deduction

    @property
    def is_terminal(self) -> bool:
        return self.terminal_status is not None


@dataclass
class StepResult:
    """What a per-line step returns. The orchestrator applies it to the context."""

    payable: Decimal
    reasons: list[Reason] = field(default_factory=list)
    terminal_status: LineItemStatus | None = None
    breached_sub_limit: bool = False
    proportionate_ratio: Decimal | None = None

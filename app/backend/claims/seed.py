"""Seed the SPEC §9 scenarios so every interesting behaviour is demoable on a fresh DB.

Run as a script (`python -m claims.seed`) to (re)create the default SQLite DB, or call
`seed(session)` from tests. Returns the created scenario claims keyed by name so tests
can assert the outcomes the demo relies on.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .domain.enums import SubLimitBasis, SubLimitType
from .domain.models import LineItemInput
from .persistence import models as orm
from .persistence.db import (
    DEFAULT_DB_URL,
    init_db,
    make_engine,
    make_session_factory,
    session_scope,
)
from .service.claims import create_claim


def _coverage_types() -> list[orm.CoverageType]:
    """The shared coverage-type catalogue. Proportionate-deduction flags follow IRDAI
    2024: room_rent triggers; surgery/OT/consultation are subject; pharmacy/diagnostics/
    implants are NOT."""
    return [
        orm.CoverageType(
            code="room_rent",
            name="Room rent",
            sub_limit_type=SubLimitType.PERCENT_OF_SI,
            sub_limit_value=Decimal("1"),
            sub_limit_basis=SubLimitBasis.PER_DAY,
            triggers_proportionate_deduction=True,
        ),
        orm.CoverageType(code="surgery", name="Surgery", subject_to_proportionate_deduction=True),
        orm.CoverageType(
            code="ot", name="Operation theatre", subject_to_proportionate_deduction=True
        ),
        orm.CoverageType(
            code="consultation", name="Consultation", subject_to_proportionate_deduction=True
        ),
        orm.CoverageType(code="pharmacy", name="Pharmacy"),
        orm.CoverageType(code="diagnostics", name="Diagnostics"),
        orm.CoverageType(code="implants", name="Implants"),
        orm.CoverageType(code="daycare", name="Daycare procedure"),
        orm.CoverageType(code="hospitalization", name="Hospitalization"),
        orm.CoverageType(code="maternity", name="Maternity", waiting_period_days=730),
        orm.CoverageType(code="cosmetic", name="Cosmetic surgery", covered=False),
        orm.CoverageType(
            code="dental",
            name="Dental",
            sub_limit_type=SubLimitType.ABSOLUTE,
            sub_limit_value=Decimal("10000"),
            sub_limit_basis=SubLimitBasis.PER_YEAR,
        ),
    ]


def _line(code: str, billed: str, **kw) -> LineItemInput:
    return LineItemInput(ref=code, coverage_type_code=code, billed_amount=Decimal(billed), **kw)


def seed(session) -> dict[str, orm.Claim]:
    # --- Plans -----------------------------------------------------------------
    plan_copay = orm.CoveragePlan(
        name="Health Secure 5L",
        description="₹5,00,000 sum insured, 10% co-pay, room rent 1% of SI/day.",
        sum_insured=Decimal("500000"),
        copay_percent=Decimal("10"),
        coverage_types=_coverage_types(),
    )
    plan_basic = orm.CoveragePlan(
        name="Aarogya Secure 3L",
        description="₹3,00,000 sum insured, no co-pay.",
        sum_insured=Decimal("300000"),
        copay_percent=Decimal("0"),
        coverage_types=_coverage_types(),
    )
    session.add_all([plan_copay, plan_basic])
    session.flush()

    # --- Members ---------------------------------------------------------------
    asha = orm.Member(name="Asha Verma", dob=date(1985, 4, 12))
    rohan = orm.Member(name="Rohan Verma", dob=date(2012, 8, 1))
    meera = orm.Member(name="Meera Nair", dob=date(1979, 11, 23))
    vikram = orm.Member(name="Vikram Rao", dob=date(1990, 2, 15))
    session.add_all([asha, rohan, meera, vikram])
    session.flush()

    # --- Policies --------------------------------------------------------------
    # Family floater: Asha (primary) + Rohan (dependent) share one sum insured.
    policy_a = orm.Policy(
        policy_number="HS5L-FAMILY-0001",
        plan_id=plan_copay.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        members=[
            orm.PolicyMember(member_id=asha.id, role="primary"),
            orm.PolicyMember(member_id=rohan.id, role="dependent"),
        ],
    )
    # Near-exhausted policy: ₹2,98,000 of ₹3,00,000 already consumed (simulating prior
    # settled claims; settlement-driven counters arrive in milestone 4).
    policy_b = orm.Policy(
        policy_number="AS3L-EXHAUST-0002",
        plan_id=plan_basic.id,
        start_date=date(2023, 6, 1),
        end_date=date(2024, 5, 31),
        sum_insured_consumed=Decimal("298000"),
        members=[orm.PolicyMember(member_id=meera.id, role="primary")],
    )
    policy_c = orm.Policy(
        policy_number="AS3L-CLEAN-0003",
        plan_id=plan_basic.id,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        members=[orm.PolicyMember(member_id=vikram.id, role="primary")],
    )
    session.add_all([policy_a, policy_b, policy_c])
    session.flush()

    claims: dict[str, orm.Claim] = {}

    # 1. Clean full approval (no co-pay, within limits) -> approved.
    claims["clean_approval"] = create_claim(
        session,
        policy_id=policy_c.id,
        member_id=vikram.id,
        service_date=date(2024, 6, 1),
        line_items=[_line("daycare", "8000"), _line("consultation", "2000")],
    )

    # 2. Room-rent + proportionate deduction (the §4.4 worked example) -> ₹41,400.
    claims["proportionate"] = create_claim(
        session,
        policy_id=policy_a.id,
        member_id=asha.id,
        service_date=date(2024, 6, 1),
        line_items=[
            _line("room_rent", "8000"),
            _line("surgery", "40000"),
            _line("pharmacy", "6000"),
            _line("diagnostics", "10000"),
        ],
    )

    # 3. Exclusion: a covered surgery alongside a non-covered cosmetic line.
    claims["exclusion"] = create_claim(
        session,
        policy_id=policy_a.id,
        member_id=asha.id,
        service_date=date(2024, 6, 15),
        line_items=[_line("surgery", "30000"), _line("cosmetic", "20000")],
    )

    # 4. Waiting period: maternity within the 730-day wait -> denied.
    claims["waiting_period"] = create_claim(
        session,
        policy_id=policy_a.id,
        member_id=asha.id,
        service_date=date(2024, 6, 1),
        line_items=[_line("maternity", "50000")],
    )

    # 5. Sum-insured exhaustion: only ₹2,000 remains -> surgery reduced to ₹2,000.
    claims["exhaustion"] = create_claim(
        session,
        policy_id=policy_b.id,
        member_id=meera.id,
        service_date=date(2024, 1, 15),
        line_items=[_line("surgery", "20000")],
    )

    # 6. Needs-review (the derived-state demo): 3 covered, 1 denied, 1 routed to review.
    claims["needs_review"] = create_claim(
        session,
        policy_id=policy_a.id,
        member_id=asha.id,
        service_date=date(2024, 7, 1),
        line_items=[
            _line("surgery", "30000"),
            _line("pharmacy", "4000"),
            _line("diagnostics", "6000"),
            _line("cosmetic", "10000"),
            _line("implants", "150000"),  # above ₹1,00,000 review threshold
        ],
    )

    # 7. Family floater: the dependent (Rohan) draws on the same policy as Asha.
    claims["family_floater"] = create_claim(
        session,
        policy_id=policy_a.id,
        member_id=rohan.id,
        service_date=date(2024, 8, 1),
        line_items=[_line("hospitalization", "15000"), _line("pharmacy", "3000")],
    )

    return claims


def main() -> None:
    engine = make_engine(DEFAULT_DB_URL)
    # Fresh DB each run so the demo is reproducible.
    orm.Base.metadata.drop_all(engine)
    init_db(engine)
    factory = make_session_factory(engine)
    with session_scope(factory) as session:
        claims = seed(session)
        print(f"Seeded {len(claims)} scenario claims into {DEFAULT_DB_URL}:")
        for name, claim in claims.items():
            session.refresh(claim)
            print(f"  - {name}: claim #{claim.id} -> {claim.status.value} / {claim.stage.value}")


if __name__ == "__main__":
    main()

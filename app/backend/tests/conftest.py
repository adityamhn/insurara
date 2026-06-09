"""Shared fixtures for persistence/service tests: a temp SQLite DB seeded with the
SPEC §9 scenarios."""

from __future__ import annotations

import pytest

from claims.persistence.db import init_db, make_engine, make_session_factory
from claims.seed import seed


@pytest.fixture
def session(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    factory = make_session_factory(engine)
    s = factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seeded(session):
    claims = seed(session)
    session.commit()
    return session, claims

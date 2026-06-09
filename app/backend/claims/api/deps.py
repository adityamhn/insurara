"""Request-scoped DB session dependency. The session factory lives on app.state so
tests can inject a seeded temp database."""

from __future__ import annotations

from typing import Iterator

from fastapi import Request
from sqlalchemy.orm import Session


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

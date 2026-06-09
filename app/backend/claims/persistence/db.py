"""Database engine, session factory, and schema creation.

Plain SQLAlchemy + `create_all` — no Alembic. Rationale (documented in
docs/decisions.md): a SQLite take-home prioritizes "clone and run"; migrations buy
nothing when the schema ships in one cut and the DB is regenerable from the seed. The
URL is swappable (env `CLAIMS_DB_URL`) so Postgres is a config change, not a rewrite.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Default local SQLite file next to the backend package.
_DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "claims.db"
DEFAULT_DB_URL = os.environ.get("CLAIMS_DB_URL", f"sqlite:///{_DEFAULT_DB_PATH}")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def make_engine(url: str = DEFAULT_DB_URL, *, echo: bool = False) -> Engine:
    # check_same_thread=False lets the dev server share one SQLite connection safely
    # under FastAPI's threadpool (single-writer dev workload).
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=echo, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all tables. Importing models registers them on Base.metadata."""
    from . import models  # noqa: F401  (registers mappers)

    Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on error, always close."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

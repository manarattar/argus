"""Database engine and session management.

Two paths to a schema, deliberately:

* **Migrations** (``make migrate``, or ``alembic upgrade head``) are the path
  every deployed environment uses. ``apps/api/alembic`` holds the revision
  chain, and ``env.py`` takes its URL from application settings so the app and
  the migration tool can never disagree about the target database. Docker runs
  ``alembic upgrade head`` before starting the API.
* **Direct creation** (:func:`init_db`) exists so ``make seed`` works on a fresh
  clone without a migration step. It is convenience for local SQLite only.

The two are kept consistent by ``alembic check``, which fails if the models have
drifted from the revision chain. ``make lint`` runs it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from argus_api.core.settings import Settings, get_settings
from argus_api.db.models import Base

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def _sqlite_path(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    _, _, raw = url.partition("///")
    return Path(raw) if raw else None


def build_engine(settings: Settings) -> Engine:
    """Create the engine, applying SQLite-specific pragmas where relevant."""
    path = _sqlite_path(settings.database_url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        settings.database_url,
        echo=False,
        future=True,
        # SQLite's default thread check trips under FastAPI's threadpool; the
        # session-per-request pattern keeps concurrent use safe regardless.
        connect_args={"check_same_thread": False} if settings.is_sqlite else {},
        pool_pre_ping=not settings.is_sqlite,
    )

    if settings.is_sqlite:

        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # WAL keeps reads from blocking the seed and evaluation writers.
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = build_engine(get_settings())
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionFactory


def init_db() -> None:
    """Create any missing tables. Safe to call repeatedly."""
    Base.metadata.create_all(bind=get_engine())


def reset_db() -> None:
    """Drop and recreate everything. Used by the seed command and tests."""
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background work."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def configure_for_tests(database_url: str) -> None:
    """Point the module at a throwaway database and rebuild the schema."""
    global _engine, _SessionFactory
    settings = get_settings()
    object.__setattr__(settings, "database_url", database_url)
    _engine = build_engine(settings)
    _SessionFactory = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)

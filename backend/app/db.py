"""SQLModel engine + session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

# SQLite requires this flag so a single connection can be used across threads
# (FastAPI spins up async handlers on a thread pool).
engine = create_engine(
    _settings.sqlite_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """Create all tables. Safe to call on every startup."""
    # Importing models here registers them with SQLModel.metadata.
    from app.models import author, institution, paper, subscription  # noqa: F401

    _settings.ensure_dirs()
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a DB session."""
    with Session(engine) as session:
        yield session

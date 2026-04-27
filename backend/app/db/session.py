"""
Async SQLAlchemy engine and session factory.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.base import Base
from app.db.migrate import apply_app_settings_patches, apply_user_patches
from app.models import AppSettings, TaskSplitEvent, User  # noqa: F401  register models

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine_url() -> str:
    """Return async database URL from settings, optionally using SQLite for tests."""
    s = get_settings()
    if s.use_sqlite:
        return "sqlite+aiosqlite:///:memory:"
    return s.database_url


def init_engine() -> None:
    """Create global engine and session factory (idempotent for tests)."""
    global _engine, _session_factory
    if _engine is not None:
        return
    url = get_engine_url()
    if url.startswith("sqlite"):
        _engine = create_async_engine(url, echo=False)
    else:
        _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False, autoflush=True
    )


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return session factory; engines must be initialized first."""
    init_engine()
    assert _session_factory is not None
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide a transactional session scope for scripts and background tasks.

    Yields:
        AsyncSession bound to a transaction, committed on success.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yield a session and close when done.

    Yields:
        Database session.
    """
    init_engine()
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_all_tables() -> None:
    """Create all ORM tables and apply lightweight patches (new columns)."""
    init_engine()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_app_settings_patches(conn)
        await apply_user_patches(conn)

"""
Declarative base and mixins for SQLAlchemy models.
"""

from datetime import datetime

from sqlalchemy import DateTime, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON as SQLAlchemyJSON
from sqlalchemy.types import TypeDecorator


class _JsonCompat(TypeDecorator):
    """JSONB on PostgreSQL, JSON on SQLite."""

    impl = Text()
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(SQLAlchemyJSON())


def json_col():
    """
    Return a compatible JSON column type for PostgreSQL and SQLite tests.

    Returns:
        TypeDecorator instance.
    """
    return _JsonCompat()


class Base(DeclarativeBase):
    """Base class for all ORM models."""


class TimestampMixin:
    """created_at / updated_at columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

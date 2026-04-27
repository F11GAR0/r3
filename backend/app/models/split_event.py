"""
History of task splits and AI-assisted operations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON as SQLAlchemyJSON
from sqlalchemy.types import TypeDecorator

from app.db.base import Base


def _json_type():
    """JSON column type compatible with PostgreSQL and SQLite."""

    class _J(TypeDecorator):
        impl = Text()
        cache_ok = True

        def load_dialect_impl(self, dialect):
            if dialect.name == "postgresql":
                return dialect.type_descriptor(JSONB())
            return dialect.type_descriptor(SQLAlchemyJSON())

    return _J()


class TaskSplitEvent(Base):
    """
    Log when a user splits a task or uses wizard actions for analytics.

    Stores Redmine issue id and human-readable summary; details in payload_json.
    """

    __tablename__ = "task_split_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    redmine_issue_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(32))
    title_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    child_issue_ids: Mapped[list | None] = mapped_column(
        _json_type(), nullable=True, default=list
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(_json_type(), default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user = relationship("User", back_populates="split_events")

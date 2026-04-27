"""
User model for local and LDAP accounts.
"""


from typing import Any

from sqlalchemy import JSON, Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import Role
from app.db.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    """
    User account: local password and/or LDAP binding.

    Local admin is created on first boot with credentials from settings.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=Role.USER, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_ldap: Mapped[bool] = mapped_column(Boolean, default=False)
    # Redmine user id for mapping actions to Redmine
    redmine_user_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    # Optional per-user Redmine API key (encrypted); used when global key has no "view users" perm.
    redmine_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Do not verify TLS to Redmine (self-signed); per-user override next to global setting
    redmine_skip_tls: Mapped[bool] = mapped_column(Boolean, default=False)
    # Per-user AI system prompts (optional overrides); merged with app defaults
    ai_prompts_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    split_events = relationship("TaskSplitEvent", back_populates="user")

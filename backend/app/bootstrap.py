"""
First-run seed: default admin and application settings row.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.roles import Role
from app.core.security import hash_password
from app.models import AppSettings, User


async def ensure_bootstrap(session: AsyncSession) -> None:
    """
    Create default admin (admin / from settings) and empty AppSettings if missing.

    Idempotent: safe to call on every application startup.

    Args:
        session: Open database session.
    """
    s = get_settings()
    r = await session.execute(select(User).where(User.username == s.first_admin_username))
    if r.scalar_one_or_none() is None:
        u = User(
            username=s.first_admin_username,
            email="admin@localhost",
            full_name="Administrator",
            role=Role.SUPERADMIN,
            hashed_password=hash_password(s.first_admin_password),
            is_ldap=False,
        )
        session.add(u)
    r2 = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    if r2.scalar_one_or_none() is None:
        session.add(
            AppSettings(
                id=1,
                sprint_lifecycle_days=s.default_sprint_lifecycle_days,
            )
        )

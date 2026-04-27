"""
Admin: user list and role assignment.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_min_role
from app.core.roles import Role, at_least
from app.db.session import get_db
from app.models import User

router = APIRouter(prefix="/api/admin", tags=["admin"])


class AdminUserOut(BaseModel):
    """User row for admin UI."""

    id: int
    username: str
    email: str | None = None
    role: str
    is_ldap: bool
    is_active: bool


class UserRolePatch(BaseModel):
    """Update user role."""

    role: str = Field(min_length=4, max_length=32)


def _to_out(u: User) -> AdminUserOut:
    return AdminUserOut(
        id=int(u.id),
        username=str(u.username),
        email=u.email,
        role=str(u.role),
        is_ldap=bool(u.is_ldap),
        is_active=bool(u.is_active),
    )


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.ADMIN))],
) -> list[AdminUserOut]:
    """List all users (admin+)."""
    r = await session.execute(select(User).order_by(User.username))
    rows = r.scalars().all()
    return [_to_out(u) for u in rows]


@router.patch("/users/{user_id}", response_model=AdminUserOut)
async def patch_user_role(
    user_id: int,
    body: UserRolePatch,
    session: Annotated[AsyncSession, Depends(get_db)],
    current: Annotated[User, Depends(require_min_role(Role.ADMIN))],
) -> AdminUserOut:
    """
    Change a user's role. Only superadmin may assign the superadmin role.
    """
    try:
        new_role = Role(body.role)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown role",
        ) from e
    try:
        cur = Role(current.role)
    except ValueError:
        cur = Role.USER
    if new_role == Role.SUPERADMIN and not at_least(cur, Role.SUPERADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superadmin can assign the superadmin role",
        )
    r = await session.execute(select(User).where(User.id == user_id))
    target = r.scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    target.role = new_role.value
    await session.flush()
    return _to_out(target)

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
from app.services.ldap_auth import lookup_ldap_user, resolve_ldap_config

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


class LdapUsernameIn(BaseModel):
    """Import or sync a user from the LDAP directory by login (no password check)."""

    username: str = Field(min_length=1, max_length=128)


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


@router.post("/users/from-ldap", response_model=AdminUserOut)
async def add_user_from_ldap(
    body: LdapUsernameIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.ADMIN))],
) -> AdminUserOut:
    """
    Find the user in LDAP (service bind + search), create a DB row or update email/name, set is_ldap.
    No password verification — use after LDAP is configured and working.
    """
    uname = body.username.strip()
    cfg = await resolve_ldap_config(session)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LDAP is not configured or not enabled for login",
        )
    info = lookup_ldap_user(uname, cfg)
    if info is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found in LDAP directory",
        )
    r = await session.execute(select(User).where(User.username == info.username))
    target = r.scalar_one_or_none()
    if target is not None:
        target.is_ldap = True
        if info.email:
            target.email = info.email
        if info.full_name:
            target.full_name = info.full_name
        await session.flush()
        return _to_out(target)
    u = User(
        username=info.username,
        email=info.email,
        full_name=info.full_name,
        role=Role.USER,
        is_ldap=True,
        hashed_password=None,
    )
    session.add(u)
    await session.flush()
    return _to_out(u)


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

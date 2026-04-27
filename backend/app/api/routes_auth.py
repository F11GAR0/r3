"""
Authentication: local password and optional LDAP, JWT response.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.roles import Role
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import User
from app.schemas.common import TokenResponse, UserOut, build_user_out
from app.services.ldap_auth import LdapUserInfo, resolve_ldap_config, try_ldap_auth

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    """Credentials for password auth."""

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


async def _get_or_create_ldap_user(session: AsyncSession, info: LdapUserInfo) -> User:
    """
    Find or create a local user row for an LDAP success.

    Args:
        session: DB session.
        info: LDAP user attributes.

    Returns:
        User ORM object.
    """
    r = await session.execute(select(User).where(User.username == info.username))
    u = r.scalar_one_or_none()
    if u:
        u.is_ldap = True
        if info.email and not u.email:
            u.email = info.email
        if info.full_name and not u.full_name:
            u.full_name = info.full_name
        return u
    u = User(
        username=info.username,
        email=info.email,
        full_name=info.full_name,
        role=Role.USER,
        is_ldap=True,
        hashed_password=None,  # type: ignore
    )
    session.add(u)
    await session.flush()
    return u


async def _local_login(session: AsyncSession, username: str, password: str) -> User | None:
    """
    Local bcrypt login for non-LDAP users (including default admin).

    Args:
        session: DB session.
        username: Login.
        password: Password.

    Returns:
        User if password matches, else None.
    """
    r = await session.execute(select(User).where(User.username == username))
    u = r.scalar_one_or_none()
    if not u or not u.hashed_password:
        return None
    if not verify_password(password, u.hashed_password):
        return None
    return u


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginIn,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """
    Exchange username/password (local or LDAP) for a signed JWT.

    On first successful LDAP login, a user row is created with role USER
    (admin can later change role via direct DB or future admin UI).

    Args:
        body: Login credentials.
        session: DB session.

    Returns:
        JWT and role string.

    Raises:
        HTTPException: 401 on failure.
    """
    cfg = await resolve_ldap_config(session)
    ldap: LdapUserInfo | None = (
        try_ldap_auth(body.username, body.password, cfg) if cfg is not None else None
    )
    if ldap is not None:
        u = await _get_or_create_ldap_user(session, ldap)
    else:
        u = await _local_login(session, body.username, body.password)
    if not u or not u.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )
    return TokenResponse(
        access_token=create_access_token(
            {
                "sub": u.username,
                "uid": u.id,
                "role": u.role,
            }
        ),
        role=u.role,
    )


@router.get("/ldap-status", response_model=dict[str, bool])
async def ldap_status(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, bool]:
    """
    Whether LDAP login is configured (DB and/or environment). Public, for login screen.
    """
    cfg = await resolve_ldap_config(session)
    return {"enabled": cfg is not None}


@router.get("/me", response_model=UserOut)
async def get_me(
    current: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Return current user profile (requires valid Bearer)."""
    return build_user_out(current)

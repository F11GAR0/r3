"""
FastAPI dependencies: DB session, current user, Redmine client, role guards.
"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto_secrets import decrypt_secret
from app.core.roles import Role, at_least
from app.core.security import decode_token
from app.db.session import get_db
from app.models import AppSettings, User
from app.services.redmine import RedmineClient

security = HTTPBearer(auto_error=False)


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Load the authenticated user from a Bearer JWT.

    Args:
        creds: Optional Authorization header.
        session: DB session.

    Returns:
        User model instance.

    Raises:
        HTTPException: If token missing, invalid, or user inactive.
    """
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    try:
        payload = decode_token(creds.credentials)
        sub = str(payload.get("sub"))
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from e
    rs = await session.execute(select(User).where(User.username == sub))
    user = rs.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_min_role(min_role: Role):
    """
    Build a dependency that requires at least a given role.

    Args:
        min_role: Minimum Role enum.

    Returns:
        Async dependency.
    """

    async def _dep(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        try:
            r = Role(user.role)
        except ValueError:
            r = Role.USER
        if not at_least(r, min_role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return _dep


def redmine_httpx_verify(c: AppSettings) -> bool:
    """
    Return httpx ``verify`` for Redmine: True = verify TLS; False = skip (self-signed).

    Only global ``AppSettings.redmine_insecure_ssl`` (admin «Настройки»).
    """
    return not bool(getattr(c, "redmine_insecure_ssl", False))


async def get_or_create_settings(session: AsyncSession) -> AppSettings:
    """
    Return global AppSettings row (id=1), creating with defaults if missing.

    Args:
        session: DB session.

    Returns:
        AppSettings model.
    """
    r = await session.execute(select(AppSettings).where(AppSettings.id == 1))
    s = r.scalar_one_or_none()
    if s is None:
        s = AppSettings(id=1)
        session.add(s)
        await session.flush()
    return s


async def make_redmine_client(session: AsyncSession) -> RedmineClient:
    """
    Build a RedmineClient from stored settings or raise 503.

    Args:
        session: DB session.

    Returns:
        Configured client.

    Raises:
        HTTPException: If not configured.
    """
    c = await get_or_create_settings(session)
    if not c.redmine_base_url or not c.redmine_api_key_encrypted:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redmine not configured"
        )
    key = decrypt_secret(c.redmine_api_key_encrypted)
    return RedmineClient(c.redmine_base_url, key, verify_ssl=redmine_httpx_verify(c))


async def make_redmine_client_for_user(session: AsyncSession, user: User) -> RedmineClient:
    """
    Use the user's own Redmine API key if set; otherwise the global key from settings.

    Per-user keys let non-admin Redmine accounts use the REST API as themselves.
    """
    c = await get_or_create_settings(session)
    if not c.redmine_base_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Redmine not configured"
        )
    v = redmine_httpx_verify(c)
    enc = getattr(user, "redmine_api_key_encrypted", None)
    if enc:
        key = decrypt_secret(str(enc))
        return RedmineClient(c.redmine_base_url, key, verify_ssl=v)
    return await make_redmine_client(session)

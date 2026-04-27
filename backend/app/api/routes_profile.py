"""
User profile: link Redmine user id for issue sync.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_or_create_settings
from app.core.crypto_secrets import decrypt_secret, encrypt_secret
from app.db.session import get_db
from app.models import AppSettings, User
from app.schemas.common import UserOut, build_user_out
from app.services.redmine import RedmineClient

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfilePatch(BaseModel):
    """Update current user's link to Redmine and optional AI prompt overrides."""

    redmine_user_id: int | None = Field(None, ge=1, description="Redmine /users me id")
    redmine_api_key: str | None = Field(
        None,
        description="Per-user key from Redmine; empty string removes stored key",
    )
    redmine_skip_tls: bool | None = Field(
        None,
        description="If True, do not verify TLS to Redmine (per-user, self-signed)",
    )
    skip_redmine_verify: bool | None = Field(
        None,
        description="If True, save id/key without calling Redmine (e.g. 403 from R3 server IP)",
    )
    ai_prompts: dict[str, str] | None = Field(
        None,
        description="Optional split_system, complexity_system, wizard_system; empty = default",
    )


def _profile_redmine_verify_ssl(
    c: AppSettings, user: User, body: ProfilePatch, fields: set[str]
) -> bool:
    """
    Httpx ``verify`` for this PATCH: global insecure flag and per-user ``redmine_skip_tls``
    (from body if present, else DB).
    """
    skip = bool(c.redmine_insecure_ssl)
    if "redmine_skip_tls" in fields:
        user_skip = bool(body.redmine_skip_tls)
    else:
        user_skip = bool(getattr(user, "redmine_skip_tls", False))
    skip = skip or user_skip
    return not skip


def _skip_redmine_verify_requested(body: ProfilePatch, fields: set[str]) -> bool:
    return "skip_redmine_verify" in fields and bool(body.skip_redmine_verify)


@router.get("", response_model=UserOut)
async def get_profile(
    user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """Return the profile for the current user."""
    return build_user_out(user)


@router.patch("", response_model=UserOut)
async def patch_profile(
    body: ProfilePatch,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> UserOut:
    """
    Set redmine_user_id and optional per-user Redmine API key for LDAP-friendly access.

    Verification does not require Redmine admin if a per-user key is used, or
    if the global key can list issues by assignee.
    """
    fields = body.model_fields_set
    c = await get_or_create_settings(session)
    if body.redmine_user_id is not None and c.redmine_base_url and not _skip_redmine_verify_requested(
        body, fields
    ):
        base = c.redmine_base_url.strip().rstrip("/")
        verify_ssl = _profile_redmine_verify_ssl(c, user, body, fields)
        incoming = (
            body.redmine_api_key.strip()
            if body.redmine_api_key is not None and body.redmine_api_key.strip()
            else None
        )
        use_personal_key = False
        rmc: RedmineClient | None = None
        if incoming:
            rmc = RedmineClient(base, incoming, verify_ssl=verify_ssl)
            use_personal_key = True
        elif user.redmine_api_key_encrypted:
            key = decrypt_secret(str(user.redmine_api_key_encrypted))
            rmc = RedmineClient(base, key, verify_ssl=verify_ssl)
            use_personal_key = True
        elif c.redmine_api_key_encrypted:
            key = decrypt_secret(str(c.redmine_api_key_encrypted))
            rmc = RedmineClient(base, key, verify_ssl=verify_ssl)
        try:
            if rmc is not None:
                await rmc.verify_redmine_user_id(
                    int(body.redmine_user_id), use_personal_key=use_personal_key
                )
        except ValueError as e:
            if rmc is not None:
                await rmc.aclose()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e
        except Exception as e:  # noqa: BLE001
            if rmc is not None:
                await rmc.aclose()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Redmine user not reachable: {e!s}",
            ) from e
        if rmc is not None:
            await rmc.aclose()
            rmc = None
    if "redmine_api_key" in fields:
        v = body.redmine_api_key
        if v is not None and not str(v).strip():
            user.redmine_api_key_encrypted = None
        elif v is not None and str(v).strip():
            user.redmine_api_key_encrypted = encrypt_secret(str(v).strip())
    if body.redmine_user_id is not None:
        user.redmine_user_id = int(body.redmine_user_id)
    if "redmine_skip_tls" in fields:
        user.redmine_skip_tls = bool(body.redmine_skip_tls)
    if body.ai_prompts is not None:
        allowed = ("split_system", "complexity_system", "wizard_system")
        pbase = dict(user.ai_prompts_json) if isinstance(user.ai_prompts_json, dict) else {}
        for k, v in body.ai_prompts.items():
            if k not in allowed:
                continue
            if not isinstance(v, str):
                continue
            if not v.strip():
                pbase.pop(k, None)
            else:
                pbase[k] = v.strip()
        user.ai_prompts_json = pbase or None
    return build_user_out(user)

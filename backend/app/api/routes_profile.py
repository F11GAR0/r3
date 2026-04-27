"""
User profile: link Redmine user id for issue sync.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_or_create_settings, make_redmine_client
from app.db.session import get_db
from app.models import User
from app.schemas.common import UserOut, build_user_out

router = APIRouter(prefix="/api/profile", tags=["profile"])


class ProfilePatch(BaseModel):
    """Update current user's link to Redmine and optional AI prompt overrides."""

    redmine_user_id: int | None = Field(None, ge=1, description="Redmine /users me id")
    ai_prompts: dict[str, str] | None = Field(
        None,
        description="Optional split_system, complexity_system, wizard_system; empty = default",
    )


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
    Set redmine_user_id. When Redmine is configured, verifies the id via
    the Redmine API (returns 400 if the user cannot be loaded).
    """
    if body.redmine_user_id is not None:
        c = await get_or_create_settings(session)
        if c.redmine_base_url and c.redmine_api_key_encrypted:
            rmc = await make_redmine_client(session)
            try:
                await rmc.get_user(int(body.redmine_user_id))
            except Exception as e:  # noqa: BLE001
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Redmine user not reachable: {e!s}",
                ) from e
            finally:
                await rmc.aclose()
        user.redmine_user_id = int(body.redmine_user_id)
    if body.ai_prompts is not None:
        allowed = ("split_system", "complexity_system", "wizard_system")
        base = dict(user.ai_prompts_json) if isinstance(user.ai_prompts_json, dict) else {}
        for k, v in body.ai_prompts.items():
            if k not in allowed:
                continue
            if not isinstance(v, str):
                continue
            if not v.strip():
                base.pop(k, None)
            else:
                base[k] = v.strip()
        user.ai_prompts_json = base or None
    return build_user_out(user)

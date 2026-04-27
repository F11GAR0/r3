"""
Task split and wizard action history.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_min_role
from app.core.roles import Role
from app.db.session import get_db
from app.models import TaskSplitEvent, User

router = APIRouter(prefix="/api/history", tags=["history"])


class SplitEventOut(BaseModel):
    """Single event row for UI."""

    id: int
    user_id: int
    username: str
    redmine_issue_id: int
    action: str
    title: str | None = None
    created_at: datetime
    payload: dict[str, Any]


@router.get("", response_model=list[SplitEventOut])
async def list_history(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    limit: int = Query(100, le=500),
) -> list[SplitEventOut]:
    """
    List recent split and wizard events for the current user.
    Admins/PMs may later extend to see all; for now own history only
    (PM backlog analytics uses stats routes).
    """
    q = (
        select(TaskSplitEvent, User.username)
        .join(User, User.id == TaskSplitEvent.user_id)
        .where(TaskSplitEvent.user_id == user.id)
        .order_by(desc(TaskSplitEvent.created_at))
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    out: list[SplitEventOut] = []
    for ev, uname in rows:
        out.append(
            SplitEventOut(
                id=ev.id,
                user_id=ev.user_id,
                username=str(uname),
                redmine_issue_id=ev.redmine_issue_id,
                action=ev.action,
                title=ev.title_snapshot,
                created_at=ev.created_at,
                payload=ev.payload_json or {},
            )
        )
    return out


@router.get("/all", response_model=list[SplitEventOut])
async def list_all_history(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.PRODUCT_MANAGER))],
    limit: int = Query(200, le=2000),
) -> list[SplitEventOut]:
    """Project-wide event log for product managers and above."""
    q = (
        select(TaskSplitEvent, User.username)
        .join(User, User.id == TaskSplitEvent.user_id)
        .order_by(desc(TaskSplitEvent.created_at))
        .limit(limit)
    )
    rows = (await session.execute(q)).all()
    return [
        SplitEventOut(
            id=ev.id,
            user_id=ev.user_id,
            username=str(uname),
            redmine_issue_id=ev.redmine_issue_id,
            action=ev.action,
            title=ev.title_snapshot,
            created_at=ev.created_at,
            payload=ev.payload_json or {},
        )
        for ev, uname in rows
    ]

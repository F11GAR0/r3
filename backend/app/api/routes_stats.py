"""
Velocity and efficiency aggregates (work days exclude weekend on client; raw series here).
"""

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_or_create_settings, make_redmine_client
from app.core.roles import Role
from app.db.session import get_db
from app.models import TaskSplitEvent, User
from app.services.redmine import list_working_days_in_range

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/summary")
async def stats_summary(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    from_date: date = Query(..., description="Start date (inclusive)"),
    to_date: date = Query(..., description="End date (inclusive)"),
    target_user_id: int | None = Query(None, description="PM: any user (internal id)"),
) -> dict:
    """
    Return split/wizard event counts and Redmine time hours for the range.

    Product managers and admins can pass target_user_id; others are limited to self.
    """
    try:
        rcur = Role(user.role)  # type: ignore
    except ValueError:
        rcur = Role.USER
    if target_user_id is not None and target_user_id != user.id:
        if rcur not in (Role.SUPERADMIN, Role.ADMIN, Role.PRODUCT_MANAGER):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only request own stats",
            )
    u = user
    if target_user_id is not None:
        r = await session.get(User, target_user_id)
        if not r:
            raise HTTPException(404, "User not found")
        u = r
    fdt = datetime.combine(from_date, datetime.min.time(), tzinfo=UTC)
    tdt = datetime.combine(to_date, datetime.max.time(), tzinfo=UTC)
    ev = select(func.count()).select_from(TaskSplitEvent).where(
        and_(
            TaskSplitEvent.user_id == u.id,
            TaskSplitEvent.created_at >= fdt,
            TaskSplitEvent.created_at <= tdt,
        )
    )
    r_count = (await session.execute(ev)).scalar_one()
    c = await get_or_create_settings(session)
    rmc = await make_redmine_client(session)
    hours = 0.0
    if u.redmine_user_id:
        try:
            te = await rmc.list_time_entries(
                int(u.redmine_user_id),
                from_str=from_date.isoformat(),
                to_str=to_date.isoformat(),
            )
            for t in te:
                hours += float(t.get("hours", 0) or 0)
        finally:
            await rmc.aclose()
    else:
        await rmc.aclose()
    working_days = list_working_days_in_range(from_date, to_date)
    return {
        "userId": u.id,
        "username": u.username,
        "splitsInPeriod": int(r_count),
        "redmineSpentHours": hours,
        "workingDaysInRange": working_days,
        "velocityHintHoursPerWorkingDay": (hours / working_days) if working_days else 0.0,
        "sprintLifecycleDays": c.sprint_lifecycle_days,
    }

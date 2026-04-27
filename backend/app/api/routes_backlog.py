"""
Product manager view: full project backlog (when project id is configured).
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_or_create_settings,
    make_redmine_client,
    require_min_role,
)
from app.core.roles import Role
from app.db.session import get_db
from app.models import User
from app.schemas.issues import IssueOut
from app.services.redmine import filter_stale_issues

from .routes_issues import _issue_to_out

router = APIRouter(prefix="/api/pm", tags=["pm"])


@router.get("/backlog", response_model=list[IssueOut])
async def pm_backlog(
    session: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_min_role(Role.PRODUCT_MANAGER))],
    only_stale: bool = True,
    sort: Literal["date", "stale", "criticality"] = "stale",
) -> list[IssueOut]:
    """
    Open issues for the configured project id (stale filter optional).
    """
    c = await get_or_create_settings(session)
    if not c.redmine_project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redmine_project_id is not set in app settings",
        )
    rmc = await make_redmine_client(session)
    try:
        issues = await rmc.list_project_issues(int(c.redmine_project_id), limit=500)
    finally:
        await rmc.aclose()
    if only_stale:
        issues = filter_stale_issues(issues, c.sprint_lifecycle_days)
    out = [_issue_to_out(i, c.redmine_complexity_field_id) for i in issues]
    if sort == "stale":
        out.sort(key=lambda x: -x.stagnation_days)
    elif sort == "criticality":
        out.sort(key=lambda x: -x.criticality)
    else:
        out.sort(key=lambda x: x.updated_on, reverse=True)
    return out

"""
Tinder-style task wizard: quick actions on a stale queue.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_or_create_settings, make_redmine_client_for_user
from app.db.session import get_db
from app.models import TaskSplitEvent, User
from app.schemas.issues import IssueOut, StatusOptionOut, WizardActionIn, WizardAIN
from app.services import ai_client
from app.services.redmine import RedmineIssue, filter_stale_issues

from .routes_issues import _issue_to_out

router = APIRouter(prefix="/api/wizard", tags=["wizard"])


def _assert_wizard_assignee(issue: RedmineIssue, user: User) -> None:
    """Wizard only operates on issues assigned to the current Redmine user."""
    if user.redmine_user_id and int(issue.assignee_id or 0) != int(user.redmine_user_id):
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Задача не назначена на вас",
        )


async def _load_issue_for_wizard(
    session: AsyncSession, user: User, issue_id: int
) -> RedmineIssue:
    rmc = await make_redmine_client_for_user(session, user)
    try:
        issue = await rmc.get_issue(issue_id)
    finally:
        await rmc.aclose()
    _assert_wizard_assignee(issue, user)
    return issue


@router.get("/queue", response_model=list[IssueOut])
async def wizard_queue(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[IssueOut]:
    """
    Return the same filtered stale list as the main backlog for Task Wizard.
    """
    c = await get_or_create_settings(session)
    rmc = await make_redmine_client_for_user(session, user)
    if not user.redmine_user_id:
        await rmc.aclose()
        raise HTTPException(400, detail="Set redmine_user_id on your profile first")
    try:
        issues = await rmc.list_user_issues(int(user.redmine_user_id), limit=200)
        issues = filter_stale_issues(issues, c.sprint_lifecycle_days)
    finally:
        await rmc.aclose()
    return [_issue_to_out(i, c.redmine_complexity_field_id) for i in issues[:50]]


@router.get("/{issue_id}/card", response_model=IssueOut)
async def wizard_card(
    issue_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> IssueOut:
    """
    Full issue row (incl. description) for the wizard card; same scope as the queue.
    """
    c = await get_or_create_settings(session)
    issue = await _load_issue_for_wizard(session, user, issue_id)
    return _issue_to_out(issue, c.redmine_complexity_field_id)


@router.get("/{issue_id}/status-options", response_model=list[StatusOptionOut])
async def wizard_status_options(
    issue_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[StatusOptionOut]:
    """
    Next allowed workflow statuses for this issue (Redmine 5+ ``allowed_statuses``),
    or open global statuses on older servers.
    """
    await _load_issue_for_wizard(session, user, issue_id)
    rmc = await make_redmine_client_for_user(session, user)
    try:
        raw = await rmc.list_allowed_statuses(issue_id)
    finally:
        await rmc.aclose()
    return [StatusOptionOut(id=int(x["id"]), name=str(x["name"])) for x in raw]


@router.post("/{issue_id}/ai-hint", response_model=dict)
async def wizard_hint(
    issue_id: int,
    body: WizardAIN,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    AI suggestions for the wizard: close, split, time, status, comment.
    """
    if not body.use_ai:
        return {"summary": "Подсказка ИИ отключена."}
    st = await get_or_create_settings(session)
    keys = list(ai_client.parse_ai_keys_json(st.ai_keys_json or []))
    if not keys:
        return {"summary": "Добавьте ключи ИИ в настройках."}
    issue = await _load_issue_for_wizard(session, user, issue_id)
    return ai_client.suggest_wizard_actions(
        issue.subject,
        issue.description or "",
        issue.status_name,
        issue.spent_hours,
        keys,
        prompts=user.ai_prompts_json,
        socks5_proxies=ai_client.parse_socks5_proxies(st.ai_socks5_proxies_json),
    )


@router.post("/{issue_id}/action", response_model=dict)
async def wizard_action(
    issue_id: int,
    body: WizardActionIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """
    Execute a wizard action in Redmine and log a TaskSplitEvent.
    """
    await get_or_create_settings(session)
    rmc = await make_redmine_client_for_user(session, user)
    try:
        issue = await rmc.get_issue(issue_id)
        _assert_wizard_assignee(issue, user)
        log_payload: dict = {"action": body.action}
        if body.action == "close":
            # Without listing statuses, use done_ratio=100
            note = body.note or "Closed from R3 wizard"
            await rmc.update_issue(issue_id, done_ratio=100, notes=note)
        elif body.action == "keep":
            pass
        elif body.action == "time" and body.hours is not None and body.hours > 0:
            await rmc.add_time_entry(issue_id, body.hours, body.note or "")
        elif body.action == "status" and body.status_id is not None:
            await rmc.update_issue(issue_id, status_id=body.status_id, notes=body.note)
        elif body.action == "comment" and body.note:
            await rmc.update_issue(issue_id, notes=body.note)
        elif body.action == "split":
            log_payload["hint"] = "use split panel to create subtasks"
        else:
            raise HTTPException(400, detail="Invalid body for this action")
        ev = TaskSplitEvent(
            user_id=user.id,
            redmine_issue_id=issue_id,
            action=f"wizard_{body.action}",
            title_snapshot=issue.subject,
            child_issue_ids=[],
            payload_json=log_payload,
        )
        session.add(ev)
    finally:
        await rmc.aclose()
    return {"ok": True, "issue_id": issue_id}

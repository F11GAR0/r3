"""
Issues: stale queue, split suggestions, subtask creation, complexity, task wizard.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_or_create_settings, make_redmine_client_for_user
from app.db.session import get_db
from app.models import TaskSplitEvent, User
from app.schemas.issues import (
    CreateSubtaskIn,
    IssueContextOut,
    IssueOut,
    RelatedIssueMini,
    SplitSuggestIn,
)
from app.services import ai_client
from app.services.redmine import COMPLEXITY_VALUES, RedmineIssue, filter_stale_issues

router = APIRouter(prefix="/api/issues", tags=["issues"])


def _issue_to_out(issue: RedmineIssue, complexity_field_id: int | None) -> IssueOut:
    """
    Map Redmine issue to API model; complexity from list field by custom field id.

    Args:
        issue: Parsed issue.
        complexity_field_id: Redmine list field id for s–2xl (or None to hide).

    Returns:
        IssueOut for JSON.
    """
    c = None
    if complexity_field_id is not None:
        raw = issue.custom_fields_by_id.get(complexity_field_id, "").strip().lower()
        if raw.replace(" ", "") in COMPLEXITY_VALUES:
            c = raw.replace(" ", "")
        elif raw in COMPLEXITY_VALUES:
            c = raw
    return IssueOut(
        id=issue.id,
        project_id=issue.project_id,
        project_name=issue.project_name,
        subject=issue.subject,
        status_id=issue.status_id,
        status_name=issue.status_name,
        priority_name=issue.priority_name,
        assignee_id=issue.assignee_id,
        created_on=issue.created_on,
        updated_on=issue.updated_on,
        stagnation_days=round(issue.stagnation_days, 2),
        life_days=round(issue.life_days, 2),
        criticality=issue.criticality,
        spent_hours=issue.spent_hours,
        estimated_hours=issue.estimated_hours,
        description=issue.description,
        complexity=c,
    )


async def _get_keys(session: AsyncSession) -> list[ai_client.APIKeyEntry]:
    """Return decrypted AI key list or empty if none."""
    c = await get_or_create_settings(session)
    return ai_client.parse_ai_keys_json(c.ai_keys_json or [])


def _split_prompt_redmine_block(issue: RedmineIssue) -> str:
    """
    Text block for the LLM: existing subtasks and relations (avoid duplicate split proposals).
    """
    parts: list[str] = []
    if issue.subtasks:
        lines = [f"  - #{s.get('id')}: {s.get('subject', '')}".strip() for s in issue.subtasks if s]
        sub_hdr = (
            "Already in Redmine — existing subtasks "
            "(do not suggest duplicates; only cover what is left):\n"
        )
        parts.append(sub_hdr + "\n".join(lines))
    if issue.related_issues:
        lines = []
        for r in issue.related_issues:
            if not r:
                continue
            rid = r.get("id")
            rtype = r.get("relation_type", "")
            subj = r.get("subject", "")
            lines.append(f"  - #{rid} [{rtype}]: {subj}".strip())
        if lines:
            rel_hdr = (
                "Already in Redmine — linked / related issues "
                "(context; align new subtasks with this work):\n"
            )
            parts.append(rel_hdr + "\n".join(lines))
    if not parts:
        return ""
    return "\n\n" + "\n\n".join(parts) + "\n"


@router.get("/{issue_id}/context", response_model=IssueContextOut)
async def get_issue_context(
    issue_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> IssueContextOut:
    """
    Subtasks, relations, and full issue details for the workbench (extra Redmine calls).
    """
    if not user.redmine_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redmine_user_id is not set for this user",
        )
    c = await get_or_create_settings(session)
    rmc = await make_redmine_client_for_user(session, user)
    try:
        issue = await rmc.get_issue(issue_id)
    finally:
        await rmc.aclose()
    if user.redmine_user_id and int(issue.assignee_id or 0) != int(user.redmine_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Задача не назначена на вас",
        )
    st_list = [
        RelatedIssueMini(id=s["id"], subject=s["subject"], relation_type="подзадача")
        for s in issue.subtasks
    ]
    rel_list = [
        RelatedIssueMini(
            id=int(r["id"]),
            subject=r.get("subject") or f"#{r['id']}",
            relation_type=str(r.get("relation_type", "связь")),
        )
        for r in issue.related_issues
    ]
    return IssueContextOut(
        issue=_issue_to_out(issue, c.redmine_complexity_field_id),
        subtasks=st_list,
        related=rel_list,
    )


@router.get("", response_model=list[IssueOut])
async def list_my_issues(
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    sort: str = Query("date", pattern="^(date|stale|criticality)$"),
    only_stale: bool = True,
) -> list[IssueOut]:
    """
    List issues assigned to the current user (requires linked Redmine user id).

    Client may request only stale (default) per sprint lifecycle, and sort
    by updated date, stagnation, or criticality.
    """
    c = await get_or_create_settings(session)
    rmc = await make_redmine_client_for_user(session, user)
    if not user.redmine_user_id:
        await rmc.aclose()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="redmine_user_id is not set for this user",
        )
    try:
        issues = await rmc.list_user_issues(int(user.redmine_user_id), limit=200)
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


@router.post("/{issue_id}/suggest-split", response_model=list[dict[str, str]])
async def suggest_split(
    issue_id: int,
    body: SplitSuggestIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, str]]:
    """
    Propose 2-4 subtasks with AI (or return empty and allow manual in UI if no keys).
    """
    keys = await _get_keys(session)
    rmc = await make_redmine_client_for_user(session, user)
    try:
        issue = await rmc.get_issue(issue_id)
    finally:
        await rmc.aclose()
    if not keys:
        return []
    if user.redmine_user_id and int(issue.assignee_id or 0) != int(user.redmine_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Задача не назначена на вас",
        )
    try:
        text = f"{issue.description or ''}\n{body.extra_prompt or ''}"
        rctx = _split_prompt_redmine_block(issue)
        return [
            {
                "subject": x["subject"],
                "description": x["description"],
            }
            for x in ai_client.suggest_task_split(
                text,
                issue.subject,
                keys,
                prompts=user.ai_prompts_json,
                redmine_context=rctx,
            )
        ]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI error: {e!s}"
        ) from e


@router.post("/{issue_id}/subtasks", response_model=IssueOut)
async def create_subtask(
    issue_id: int,
    body: CreateSubtaskIn,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> IssueOut:
    """
    Create a child issue under the given parent (split without AI is allowed).
    """
    await get_or_create_settings(session)
    rmc = await make_redmine_client_for_user(session, user)
    try:
        parent = await rmc.get_issue(issue_id)
        cf_payload: list[dict[str, Any]] = [
            {"id": int(cid), "value": str(val)}
            for cid, val in parent.custom_fields_by_id.items()
            if str(val).strip() != ""
        ]
        created = await rmc.create_issue(
            parent.project_id,
            body.subject,
            body.description,
            parent_issue_id=issue_id,
            assignee_id=parent.assignee_id,
            tracker_id=parent.tracker_id or None,
            fixed_version_id=parent.fixed_version_id,
            priority_id=parent.priority_id,
            category_id=parent.category_id,
            custom_fields=cf_payload or None,
        )
        ev = TaskSplitEvent(
            user_id=user.id,
            redmine_issue_id=issue_id,
            action="split",
            title_snapshot=parent.subject,
            child_issue_ids=[created.id],
            payload_json={"subject": body.subject},
        )
        session.add(ev)
    finally:
        await rmc.aclose()
    cset = await get_or_create_settings(session)
    return _issue_to_out(created, cset.redmine_complexity_field_id)


@router.post("/{issue_id}/suggest-complexity", response_model=dict[str, str])
async def suggest_complexity(
    issue_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    """
    Suggest t-shirt size using AI. Returns { "value": "m" }.
    """
    keys = await _get_keys(session)
    if not keys:
        raise HTTPException(status_code=400, detail="No AI keys configured")
    rmc = await make_redmine_client_for_user(session, user)
    try:
        issue = await rmc.get_issue(issue_id)
    finally:
        await rmc.aclose()
    try:
        v = ai_client.suggest_complexity(
            issue.subject, issue.description or "", keys, prompts=user.ai_prompts_json
        )
        return {"value": v if v in COMPLEXITY_VALUES else "m"}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(e)) from e


@router.put("/{issue_id}/complexity", response_model=dict[str, str])
async def set_complexity(
    issue_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    value: str = Query(..., pattern="^(s|m|l|xl|2xl)$"),
) -> dict[str, str]:
    """
    Persist complexity: updates description line if no custom field id in settings
    (Redmine may need custom field id for full support — we store in description prefix).
    """
    cfg = await get_or_create_settings(session)
    fid = cfg.redmine_complexity_field_id
    if fid is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Set redmine_complexity_field_id in settings (Redmine list field for s–2xl)",
        )
    rmc = await make_redmine_client_for_user(session, user)
    try:
        await rmc.set_complexity_label(issue_id, value, custom_field_id=fid)
    finally:
        await rmc.aclose()
    return {"value": value}

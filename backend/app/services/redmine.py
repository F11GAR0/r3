"""
Redmine REST API client (issues, time entries, custom fields, labels as tags in some setups).
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

import httpx

COMPLEXITY_VALUES = ("s", "m", "l", "xl", "2xl")


@dataclass
class RedmineIssue:
    """Simplified issue for API responses."""

    id: int
    project_id: int
    project_name: str
    subject: str
    description: str
    status_id: int
    status_name: str
    priority_id: int
    priority_name: str
    author_id: int
    assignee_id: int | None
    created_on: datetime
    updated_on: datetime
    done_ratio: int
    estimated_hours: float | None = None
    spent_hours: float = 0.0
    custom_fields: dict[str, str] = field(default_factory=dict)
    custom_fields_by_id: dict[int, str] = field(default_factory=dict)
    tracker_id: int = 0
    tags: list[str] = field(default_factory=list)  # from category or custom
    fixed_version_id: int | None = None
    category_id: int | None = None
    parent_issue_id: int | None = None
    # Filled on issue#show: children (subtasks) and cross-issue relations (subjects from extra GETs)
    subtasks: list[dict[str, Any]] = field(default_factory=list)
    related_issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def stagnation_days(self) -> float:
        """
        Days since last update (proxy for 'staleness' when workflow metadata is missing).

        Returns:
            Floating days between now and updated_on.
        """
        now = datetime.now(UTC)
        u = self.updated_on
        if u.tzinfo is None:
            u = u.replace(tzinfo=UTC)
        return max(0.0, (now - u).total_seconds() / 86400.0)

    @property
    def life_days(self) -> float:
        """
        Days from creation to now.

        Returns:
            Age in days of the issue.
        """
        now = datetime.now(UTC)
        c = self.created_on
        if c.tzinfo is None:
            c = c.replace(tzinfo=UTC)
        return (now - c).total_seconds() / 86400.0

    @property
    def criticality(self) -> int:
        """
        Heuristic 1–5 score from priority id (higher = more urgent in typical Redmine).

        Returns:
            Integer score for sorting.
        """
        if self.priority_id <= 0:
            return 2
        return min(5, max(1, 1 + (self.priority_id % 5)))


def _parse_dt(s: str) -> datetime:
    """Parse Redmine datetime string to UTC-aware datetime."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d


def _parse_issue(raw: dict[str, Any]) -> RedmineIssue:
    """Map Redmine JSON issue to RedmineIssue."""
    pr = raw.get("project", {}) or {}
    st = raw.get("status", {}) or {}
    prd = raw.get("priority", {}) or {}
    au = raw.get("author", {}) or {}
    asg = raw.get("assigned_to")
    cfields: dict[str, str] = {}
    cfields_by_id: dict[int, str] = {}
    for cf in raw.get("custom_fields") or []:
        name = str(cf.get("name", ""))
        cid = cf.get("id")
        val = cf.get("value")
        if isinstance(val, list):
            sval = ", ".join(str(x) for x in val)
        else:
            sval = str(val) if val is not None else ""
        if name:
            cfields[name] = sval
        if cid is not None:
            try:
                cfields_by_id[int(cid)] = sval
            except (TypeError, ValueError):
                pass
    tags: list[str] = []
    if raw.get("category") and (raw.get("category") or {}).get("name"):
        tags.append(str((raw.get("category") or {}).get("name")))
    fv = raw.get("fixed_version")
    fixed_version_id = int(fv["id"]) if isinstance(fv, dict) and fv.get("id") is not None else None
    cat = raw.get("category")
    category_id = int(cat["id"]) if isinstance(cat, dict) and cat.get("id") is not None else None
    par = raw.get("parent")
    parent_issue_id = (
        int(par["id"])
        if isinstance(par, dict) and par.get("id") is not None
        else None
    )
    return RedmineIssue(
        id=int(raw["id"]),
        project_id=int(pr.get("id", 0)),
        project_name=str(pr.get("name", "")),
        subject=str(raw.get("subject", "")),
        description=str(raw.get("description", "")),
        status_id=int((st or {}).get("id", 0)),
        status_name=str((st or {}).get("name", "")),
        priority_id=int((prd or {}).get("id", 0)),
        priority_name=str((prd or {}).get("name", "")),
        author_id=int((au or {}).get("id", 0)),
        assignee_id=int(asg["id"]) if asg and asg.get("id") is not None else None,
        created_on=_parse_dt(str(raw.get("created_on", ""))),
        updated_on=_parse_dt(str(raw.get("updated_on", ""))),
        done_ratio=int(raw.get("done_ratio", 0)),
        estimated_hours=float(raw["estimated_hours"])
        if raw.get("estimated_hours") is not None
        else None,
        spent_hours=float(raw.get("spent_hours", 0) or 0),
        custom_fields=cfields,
        custom_fields_by_id=cfields_by_id,
        tracker_id=int((raw.get("tracker") or {}).get("id", 0) or 0),
        tags=tags,
        fixed_version_id=fixed_version_id,
        category_id=category_id,
        parent_issue_id=parent_issue_id,
    )


class RedmineClient:
    """
    Async HTTP client for common Redmine operations.

    Args:
        base_url: e.g. https://redmine.example.com
        api_key: Redmine API key in header X-Redmine-API-Key
    """

    def __init__(self, base_url: str, api_key: str, *, verify_ssl: bool = True) -> None:
        """
        Args:
            base_url: Redmine base URL.
            api_key: REST API key.
            verify_ssl: Set False for self-signed certificates (insecure).
        """
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"X-Redmine-API-Key": self._key, "Content-Type": "application/json"},
            timeout=httpx.Timeout(60.0),
            verify=verify_ssl,
        )

    async def aclose(self) -> None:
        """Close the underlying httpx client."""
        await self._client.aclose()

    async def get_user(self, user_id: int) -> dict[str, Any]:
        """
        Fetch Redmine user by id (for verifying profile link).

        Args:
            user_id: Numeric id.

        Returns:
            The `user` object from Redmine.
        """
        r = await self._client.get(f"/users/{user_id}.json")
        r.raise_for_status()
        return r.json()["user"]

    async def current_user_id(self) -> int:
        """
        Return id of the user that owns the API key.

        Returns:
            Numeric Redmine user id.
        """
        r = await self._client.get("/users/current.json")
        r.raise_for_status()
        return int(r.json()["user"]["id"])

    async def list_user_issues(
        self,
        user_id: int,
        include_closed: bool = False,
        limit: int = 100,
    ) -> list[RedmineIssue]:
        """
        List issues assigned to a user (open by default).

        Args:
            user_id: Redmine assignee id.
            include_closed: If True, do not filter by status.
            limit: Max issues.

        Returns:
            Parsed issues, newest first.
        """
        params: dict[str, Any] = {
            "assigned_to_id": user_id,
            "limit": limit,
            "sort": "updated_on:desc",
            "include": "project,tracker,status,assigned_to,author",
        }
        if not include_closed:
            params["status_id"] = "open"
        r = await self._client.get("/issues.json", params=params)
        r.raise_for_status()
        return [_parse_issue(x) for x in r.json().get("issues", [])]

    async def list_project_issues(
        self,
        project_id: int,
        limit: int = 200,
    ) -> list[RedmineIssue]:
        """
        List open issues in a project for backlog/PM view.

        Args:
            project_id: Redmine project id.
            limit: Max issues.

        Returns:
            Parsed issues.
        """
        params: dict[str, Any] = {
            "project_id": project_id,
            "status_id": "open",
            "limit": limit,
            "include": "project,tracker,status,assigned_to,author",
            "sort": "updated_on:desc",
        }
        r = await self._client.get("/issues.json", params=params)
        r.raise_for_status()
        return [_parse_issue(x) for x in r.json().get("issues", [])]

    async def get_issue(self, issue_id: int) -> RedmineIssue:
        """
        Fetch a single issue by id.

        Args:
            issue_id: Redmine id.

        Returns:
            Parsed issue, with subtasks/related (subjects) when present in Redmine.
        """
        inc = (
            "children,relations,project,status,tracker,category,"
            "author,assigned_to,fixed_version"
        )
        r = await self._client.get(f"/issues/{issue_id}.json", params={"include": inc})
        r.raise_for_status()
        issue_raw = r.json()["issue"]
        issue = _parse_issue(issue_raw)
        subtasks: list[dict[str, Any]] = []
        for c in issue_raw.get("children") or []:
            if not isinstance(c, dict):
                continue
            try:
                cid = int(c.get("id", 0))
            except (TypeError, ValueError):
                continue
            subtasks.append(
                {
                    "id": cid,
                    "subject": str(c.get("subject", "")).strip() or f"#{cid}",
                }
            )
        rel_entries: list[dict[str, Any]] = []
        seen: set[int] = set()
        for rel in issue_raw.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            try:
                a = int(rel.get("issue_id", 0))
                b = int(rel.get("issue_to_id", 0))
            except (TypeError, ValueError):
                continue
            other = b if a == issue_id else a if b == issue_id else 0
            if not other or other in seen:
                continue
            seen.add(other)
            rtype = str(rel.get("relation_type", "relates"))
            rel_entries.append({"id": other, "relation_type": rtype, "subject": ""})
        # Resolve relation subjects
        for item in rel_entries:
            oid = int(item["id"])
            br = await self._client.get(f"/issues/{oid}.json", params={"include": "project"})
            if br.is_success:
                try:
                    item["subject"] = str(
                        (br.json().get("issue") or {}).get("subject", "") or f"#{oid}"
                    )
                except (TypeError, KeyError, ValueError):
                    item["subject"] = f"#{oid}"
        issue.subtasks = subtasks
        issue.related_issues = rel_entries
        return issue

    async def create_issue(
        self,
        project_id: int,
        subject: str,
        description: str,
        parent_issue_id: int | None = None,
        assignee_id: int | None = None,
        tracker_id: int | None = None,
        fixed_version_id: int | None = None,
        priority_id: int | None = None,
        category_id: int | None = None,
        custom_fields: list[dict[str, Any]] | None = None,
    ) -> RedmineIssue:
        """
        Create a new issue, optionally as a subtask.

        Args:
            project_id: Target project.
            subject: Title.
            description: Text body.
            parent_issue_id: If set, link as sub-issue.
            assignee_id: Optional assignee.
            tracker_id: Optional tracker; server default if None.
            fixed_version_id: Optional sprint / version.
            priority_id: Optional priority to mirror parent.
            category_id: Optional category to mirror parent.
            custom_fields: Optional ``[{ "id", "value" }]`` copied from parent.

        Returns:
            Created issue.
        """
        body: dict[str, Any] = {
            "issue": {
                "project_id": project_id,
                "subject": subject,
                "description": description,
            }
        }
        if parent_issue_id is not None:
            body["issue"]["parent_issue_id"] = parent_issue_id
        if assignee_id is not None:
            body["issue"]["assigned_to_id"] = assignee_id
        if tracker_id is not None:
            body["issue"]["tracker_id"] = tracker_id
        if fixed_version_id is not None:
            body["issue"]["fixed_version_id"] = fixed_version_id
        if priority_id is not None:
            body["issue"]["priority_id"] = priority_id
        if category_id is not None:
            body["issue"]["category_id"] = category_id
        if custom_fields:
            body["issue"]["custom_fields"] = custom_fields
        r = await self._client.post("/issues.json", json=body)
        r.raise_for_status()
        return _parse_issue(r.json()["issue"])

    async def update_issue(
        self,
        issue_id: int,
        *,
        status_id: int | None = None,
        notes: str | None = None,
        done_ratio: int | None = None,
    ) -> None:
        """
        Update issue status and/or add journal note.

        Args:
            issue_id: Redmine id.
            status_id: New workflow status.
            notes: Optional comment to journal.
            done_ratio: Optional percent complete.
        """
        ch: dict[str, Any] = {}
        if status_id is not None:
            ch["status_id"] = status_id
        if done_ratio is not None:
            ch["done_ratio"] = done_ratio
        body: dict[str, Any] = {"issue": ch}
        if notes:
            body["issue"]["notes"] = notes
        r = await self._client.put(f"/issues/{issue_id}.json", json=body)
        r.raise_for_status()

    async def list_allowed_statuses(self, issue_id: int) -> list[dict[str, Any]]:
        """
        List statuses the current API user can switch this issue to.

        Redmine 5+ returns ``allowed_statuses`` in issue JSON. Older servers: all
        open global statuses (may include transitions the workflow will reject).
        """
        r = await self._client.get(
            f"/issues/{issue_id}.json",
            params={"include": "allowed_statuses"},
        )
        r.raise_for_status()
        issue_raw = r.json().get("issue", {}) or {}
        allowed = issue_raw.get("allowed_statuses")
        out: list[dict[str, Any]] = []
        if isinstance(allowed, list) and len(allowed) > 0:
            for s in allowed:
                if not isinstance(s, dict) or s.get("id") is None:
                    continue
                out.append(
                    {
                        "id": int(s["id"]),
                        "name": str(s.get("name", "")),
                    }
                )
            return out
        r2 = await self._client.get("/issue_statuses.json")
        r2.raise_for_status()
        for s in r2.json().get("issue_statuses", []):
            if not isinstance(s, dict) or s.get("id") is None:
                continue
            if s.get("is_closed"):
                continue
            out.append(
                {
                    "id": int(s["id"]),
                    "name": str(s.get("name", "")),
                }
            )
        return out

    async def list_time_entries(
        self,
        user_id: int,
        from_str: str | None = None,
        to_str: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List time entries for a user (ISO date strings for from/to, optional).

        Args:
            user_id: Redmine user id.
            from_str: YYYY-MM-DD
            to_str: YYYY-MM-DD

        Returns:
            List of time_entry objects from Redmine.
        """
        params: dict[str, Any] = {"user_id": user_id, "limit": 200}
        if from_str:
            params["from"] = from_str
        if to_str:
            params["to"] = to_str
        r = await self._client.get("/time_entries.json", params=params)
        r.raise_for_status()
        return [x.get("time_entry", x) for x in r.json().get("time_entries", [])]

    async def add_time_entry(
        self, issue_id: int, hours: float, comment: str = "", activity_id: int = 8
    ) -> None:
        """
        Add spent time to an issue (activity 8 = Development in default Redmine).

        Args:
            issue_id: Target issue.
            hours: Spent time.
            comment: Work note.
            activity_id: Time activity (Redmine setting dependent).
        """
        body = {
            "time_entry": {
                "issue_id": issue_id,
                "hours": hours,
                "activity_id": activity_id,
            }
        }
        if comment:
            body["time_entry"]["comments"] = comment
        r = await self._client.post("/time_entries.json", json=body)
        r.raise_for_status()

    async def set_complexity_label(self, issue_id: int, value: str, custom_field_id: int) -> None:
        """
        Set the list custom field in Redmine to a t-shirt value (s, m, l, xl, 2xl).

        Args:
            issue_id: Issue id.
            value: One of s,m,l,xl,2xl
            custom_field_id: Redmine list field id (same as in administration → custom fields).
        """
        v = value.lower()
        if v not in COMPLEXITY_VALUES:
            msg = f"Invalid complexity {value}"
            raise ValueError(msg)
        body = {"issue": {"custom_fields": [{"id": custom_field_id, "value": v}]}}
        r = await self._client.put(f"/issues/{issue_id}.json", json=body)
        r.raise_for_status()


def filter_stale_issues(
    issues: list[RedmineIssue],
    sprint_lifecycle_days: int,
) -> list[RedmineIssue]:
    """
    Keep issues not updated for longer than sprint_lifecycle_days (staleness rule).

    Args:
        issues: All candidate issues.
        sprint_lifecycle_days: Threshold in days from settings.

    Returns:
        Subset that exceeds the threshold.
    """
    return [i for i in issues if i.stagnation_days >= float(sprint_lifecycle_days)]


def is_working_day(d: date) -> bool:
    """
    Return False for Saturday/Sunday; used for capacity stats.

    Args:
        d: Calendar date in local org TZ (callers set TZ).

    Returns:
        True if Mon–Fri.
    """
    return d.weekday() < 5


def list_working_days_in_range(start: date, end: date) -> int:
    """
    Count Mon–Fri days inclusive between start and end.

    Args:
        start: Range start.
        end: Range end (inclusive).

    Returns:
        Count of working days.
    """
    n = 0
    cur = start
    while cur <= end:
        if is_working_day(cur):
            n += 1
        cur = date.fromordinal(cur.toordinal() + 1)
    return n


def velocity_from_issues(
    closed_issues: list[dict[str, Any]],
) -> float:
    """
    Sum story points or estimated hours from a list of Redmine issue dicts (closed period).

    Uses estimated_hours if present, else 1 point per issue.

    Args:
        closed_issues: Raw or simplified dicts with optional estimated_hours.

    Returns:
        Float story points.
    """
    s = 0.0
    for it in closed_issues:
        h = it.get("estimated_hours")
        if h is not None:
            s += float(h)
        else:
            s += 1.0
    return s

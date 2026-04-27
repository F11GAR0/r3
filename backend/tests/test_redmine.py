"""
Unit tests for Redmine client helpers (no network).
"""

from datetime import UTC, datetime

from app.services.redmine import (
    RedmineIssue,
    filter_stale_issues,
    is_working_day,
    list_working_days_in_range,
    velocity_from_issues,
)

now = datetime(2020, 1, 10, 12, 0, tzinfo=UTC)
old = datetime(2019, 1, 1, 0, 0, tzinfo=UTC)


def _issue(stagnation: float) -> RedmineIssue:
    """Build a RedmineIssue with contrived updated_on for stale testing."""
    return RedmineIssue(
        id=1,
        project_id=1,
        project_name="p",
        subject="s",
        description="",
        status_id=1,
        status_name="o",
        priority_id=3,
        priority_name="h",
        author_id=1,
        assignee_id=1,
        created_on=old,
        updated_on=old,
        done_ratio=0,
        spent_hours=0,
    )


def test_filter_stale_issues() -> None:
    """
    filter_stale_issues keeps issues whose updated_on is far enough in the past.
    """
    from datetime import timedelta
    from unittest.mock import patch  # noqa: PLC0415

    fixed = datetime(2020, 2, 1, 12, 0, tzinfo=UTC)
    i_stale = _issue(1.0)
    i_stale.updated_on = fixed - timedelta(days=20)
    i_fresh = _issue(1.0)
    i_fresh.updated_on = fixed - timedelta(days=1)
    with patch("app.services.redmine.datetime") as mdt:
        mdt.now = lambda tz=None: fixed
        mdt.fromisoformat = datetime.fromisoformat
        mdt.combine = datetime.combine
        res = filter_stale_issues([i_stale, i_fresh], 14)
    assert len(res) == 1
    assert res[0] is i_stale


def test_working_days() -> None:
    """
    is_working_day and list_working_days_in_range should skip weekend.
    """
    from datetime import date

    mon = date(2024, 1, 1)  # Monday
    assert is_working_day(mon) is True
    sat = date(2024, 1, 6)  # Saturday
    assert is_working_day(sat) is False
    assert list_working_days_in_range(date(2024, 1, 1), date(2024, 1, 7)) == 5


def test_velocity_from_issues() -> None:
    """
    velocity_from_issues should sum estimated_hours or 1 per item.
    """
    assert abs(velocity_from_issues([{"estimated_hours": 2.0}]) - 2.0) < 0.01
    assert abs(velocity_from_issues([{}]) - 1.0) < 0.01

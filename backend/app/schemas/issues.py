"""
Issue-related request/response models.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class IssueOut(BaseModel):
    """Issue card for UI list."""

    id: int
    project_id: int
    project_name: str
    subject: str
    status_id: int = 0
    status_name: str
    priority_name: str
    assignee_id: int | None = None
    created_on: datetime
    updated_on: datetime
    stagnation_days: float
    life_days: float
    criticality: int
    spent_hours: float
    estimated_hours: float | None = None
    description: str = ""
    complexity: str | None = None


class SplitSuggestionItem(BaseModel):
    """One proposed subtask."""

    subject: str
    description: str


class SplitSuggestIn(BaseModel):
    """Optional manual context for split."""

    extra_prompt: str = ""


class CreateSubtaskIn(BaseModel):
    """Create child issue from proposal."""

    subject: str
    description: str


class RelatedIssueMini(BaseModel):
    """Child or related issue for workbench context."""

    id: int
    subject: str
    relation_type: str | None = None


class IssueContextOut(BaseModel):
    """Selected issue with subtasks and cross-links from Redmine."""

    issue: IssueOut
    subtasks: list[RelatedIssueMini] = Field(default_factory=list)
    related: list[RelatedIssueMini] = Field(default_factory=list)


class WizardActionIn(BaseModel):
    """Task wizard action without AI."""

    action: str = Field(
        pattern="^(close|keep|time|status|comment|split)$",
        description="close|keep|time|status|comment|split",
    )
    hours: float | None = None
    status_id: int | None = None
    note: str | None = None


class WizardAIN(BaseModel):
    """Ask AI for wizard hints."""

    use_ai: bool = True


class StatusOptionOut(BaseModel):
    """One workflow target status (from Redmine allowed_statuses or fallback)."""

    id: int
    name: str

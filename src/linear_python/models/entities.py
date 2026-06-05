"""Pydantic models for Linear API entities.

All models use snake_case attribute names with automatically generated camelCase
aliases, so they parse the API's camelCase payloads (`displayName`, `createdAt`,
…) and can be serialised back to them with `model_dump(by_alias=True)`. Because
`populate_by_name=True`, you can construct them with either spelling.

Only the fields a given query requested are populated; everything is optional and
defaults to `None`, and unknown fields are ignored.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel


class LinearModel(BaseModel):
    """Base model: camelCase aliases, snake_case attributes, lenient parsing."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="ignore",
    )


class PageInfo(LinearModel):
    """Relay-style pagination metadata for a connection."""

    has_next_page: bool = False
    has_previous_page: bool = False
    start_cursor: str | None = None
    end_cursor: str | None = None


class User(LinearModel):
    """A Linear user."""

    id: str | None = None
    name: str | None = None
    display_name: str | None = None
    email: str | None = None
    active: bool | None = None
    admin: bool | None = None
    created_at: datetime | None = None


class Team(LinearModel):
    """A Linear team."""

    id: str | None = None
    name: str | None = None
    key: str | None = None
    description: str | None = None
    private: bool | None = None
    created_at: datetime | None = None


class WorkflowState(LinearModel):
    """An issue workflow state (e.g. Todo, In Progress, Done)."""

    id: str | None = None
    name: str | None = None
    type: str | None = None
    color: str | None = None
    position: float | None = None


class IssueLabel(LinearModel):
    """A label that can be applied to issues."""

    id: str | None = None
    name: str | None = None
    color: str | None = None


class Project(LinearModel):
    """A Linear project."""

    id: str | None = None
    name: str | None = None
    description: str | None = None
    slug_id: str | None = None
    state: str | None = None
    progress: float | None = None
    created_at: datetime | None = None


class Comment(LinearModel):
    """A comment on an issue."""

    id: str | None = None
    body: str | None = None
    url: str | None = None
    user: User | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Issue(LinearModel):
    """A Linear issue, with nested relations populated when requested."""

    id: str | None = None
    identifier: str | None = None
    title: str | None = None
    description: str | None = None
    url: str | None = None
    priority: int | None = None
    estimate: float | None = None
    branch_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    assignee: User | None = None
    creator: User | None = None
    team: Team | None = None
    state: WorkflowState | None = None
    labels: list[IssueLabel] = Field(default_factory=list)

    @field_validator("labels", mode="before")
    @classmethod
    def _unwrap_label_nodes(cls, value: object) -> object:
        """Accept Linear's `labels: { nodes: [...] }` connection shape."""
        if isinstance(value, dict) and "nodes" in value:
            return value["nodes"]
        return value

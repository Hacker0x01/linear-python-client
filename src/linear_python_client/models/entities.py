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


def _unwrap_nodes(value: object) -> object:
    """Accept Linear's `{ nodes: [...] }` connection shape, returning the node list."""
    if isinstance(value, dict) and "nodes" in value:
        return value["nodes"]
    return value


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
        return _unwrap_nodes(value)


class Attachment(LinearModel):
    """A link or file attached to an issue."""

    id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    url: str | None = None
    created_at: datetime | None = None


class Cycle(LinearModel):
    """A team cycle (sprint)."""

    id: str | None = None
    number: int | None = None
    name: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class IssueRelation(LinearModel):
    """A relation from an issue to another (e.g. blocks, related, duplicate)."""

    type: str | None = None
    related_issue: Issue | None = None


class IssueDetail(Issue):
    """An issue plus its heavier related data, returned by `issue_details`.

    Inherits every field of [`Issue`][linear_python_client.Issue] and adds the
    related collections. As always, only the fields the query requested are
    populated; `parent`, `children`, and relation targets are shallow issues.
    """

    comments: list[Comment] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    project: Project | None = None
    cycle: Cycle | None = None
    parent: Issue | None = None
    children: list[Issue] = Field(default_factory=list)
    subscribers: list[User] = Field(default_factory=list)
    relations: list[IssueRelation] = Field(default_factory=list)

    @field_validator(
        "comments", "attachments", "children", "subscribers", "relations", mode="before"
    )
    @classmethod
    def _unwrap_connection_nodes(cls, value: object) -> object:
        """Accept Linear's `{ nodes: [...] }` connection shape for the collections."""
        return _unwrap_nodes(value)

"""Typed request models for each :class:`~linear_python_client.client.LinearClient` call.

Every client method takes exactly one of these. They carry snake_case fields with
camelCase aliases, and expose helpers (`to_variables`, `to_input`) that serialise
them into the GraphQL variables the API expects.
"""

from __future__ import annotations

from typing import Any

from pydantic import ConfigDict, Field

from .entities import LinearModel

# -- query requests ---------------------------------------------------------


class IssueRequest(LinearModel):
    """Fetch a single issue by id or human identifier (e.g. `"ENG-123"`)."""

    id: str


class UserRequest(LinearModel):
    """Fetch a single user by UUID."""

    id: str


class TeamRequest(LinearModel):
    """Fetch a single team by UUID."""

    id: str


class ProjectRequest(LinearModel):
    """Fetch a single project by UUID."""

    id: str


class CommentRequest(LinearModel):
    """Fetch a single comment by UUID."""

    id: str


class PaginatedRequest(LinearModel):
    """Base for list requests: cursor pagination plus an optional filter.

    Attributes:
        first: Maximum number of results to return (Linear defaults to 50).
        after: Pagination cursor; pass the previous page's `end_cursor`.
        filter: A [Linear filter](https://linear.app/developers/filtering) dict.
    """

    first: int | None = None
    after: str | None = None
    filter: dict[str, Any] | None = None

    def to_variables(self) -> dict[str, Any]:
        """Serialise to GraphQL variables (camelCase, omitting unset values)."""
        return self.model_dump(by_alias=True, exclude_none=True)


class IssuesRequest(PaginatedRequest):
    """List issues, optionally filtered and ordered.

    Attributes:
        order_by: Sort order, either `"createdAt"` (default) or `"updatedAt"`.
    """

    order_by: str | None = None


class UsersRequest(PaginatedRequest):
    """List users in the workspace."""


class TeamsRequest(PaginatedRequest):
    """List teams in the workspace."""


class ProjectsRequest(PaginatedRequest):
    """List projects in the workspace."""


class IssueLabelsRequest(PaginatedRequest):
    """List issue labels in the workspace."""


class CommentsRequest(PaginatedRequest):
    """List comments, optionally scoped to a single issue.

    Attributes:
        issue_id: When set, only comments on this issue are returned (merged into
            `filter`). Not sent as a raw variable.
    """

    issue_id: str | None = Field(default=None, exclude=True)


class WorkflowStatesRequest(PaginatedRequest):
    """List workflow states, optionally scoped to a single team.

    Attributes:
        team_id: When set, only states belonging to this team are returned (merged
            into `filter`). Not sent as a raw variable.
    """

    team_id: str | None = Field(default=None, exclude=True)


# -- mutation requests ------------------------------------------------------


class IssueCreateRequest(LinearModel):
    """Input for creating an issue.

    Any field accepted by Linear's `IssueCreateInput` may also be passed as an
    extra keyword argument using its camelCase API name (e.g. `dueDate="2026-01-01"`).

    Attributes:
        team_id: UUID of the team the issue belongs to (required).
        title: The issue title (required).
        description: Markdown body for the issue.
        assignee_id: UUID of the user to assign.
        state_id: UUID of the workflow state to set.
        priority: Priority from 0 (none) to 4 (low); 1 is urgent.
        label_ids: UUIDs of labels to attach.
        project_id: UUID of the project to add the issue to.
    """

    model_config = ConfigDict(extra="allow")

    team_id: str
    title: str
    description: str | None = None
    assignee_id: str | None = None
    state_id: str | None = None
    priority: int | None = None
    label_ids: list[str] | None = None
    project_id: str | None = None

    def to_input(self) -> dict[str, Any]:
        """Serialise to an `IssueCreateInput` dict (camelCase, omitting unset values)."""
        return self.model_dump(by_alias=True, exclude_none=True)


class IssueUpdateRequest(LinearModel):
    """Input for updating an issue.

    At least one field other than `id` must be set. Any field accepted by Linear's
    `IssueUpdateInput` may also be passed as an extra keyword argument using its
    camelCase API name.

    Attributes:
        id: UUID of the issue to update (required).
        title: New title.
        description: New markdown body.
        assignee_id: UUID of the user to assign.
        state_id: UUID of the workflow state to set.
        priority: Priority from 0 (none) to 4 (low); 1 is urgent.
        label_ids: UUIDs of labels to set.
        project_id: UUID of the project to move the issue to.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    title: str | None = None
    description: str | None = None
    assignee_id: str | None = None
    state_id: str | None = None
    priority: int | None = None
    label_ids: list[str] | None = None
    project_id: str | None = None

    def to_input(self) -> dict[str, Any]:
        """Serialise the update fields to an `IssueUpdateInput` dict (excluding `id`)."""
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("id", None)
        return data


class IssueArchiveRequest(LinearModel):
    """Archive an issue by UUID."""

    id: str


class IssueAddLabelRequest(LinearModel):
    """Add a single label to an issue, leaving its other labels untouched.

    Attributes:
        id: UUID of the issue.
        label_id: UUID of the label to add.
    """

    id: str
    label_id: str


class IssueRemoveLabelRequest(LinearModel):
    """Remove a single label from an issue, leaving its other labels untouched.

    Attributes:
        id: UUID of the issue.
        label_id: UUID of the label to remove.
    """

    id: str
    label_id: str


class IssueSetStateRequest(LinearModel):
    """Move an issue to a workflow state (status).

    Attributes:
        id: UUID of the issue.
        state_id: UUID of the target workflow state. Resolve one by name with
            [`find_workflow_state`][linear_python_client.client.LinearClient.find_workflow_state].
    """

    id: str
    state_id: str


class FindWorkflowStateRequest(LinearModel):
    """Resolve a workflow state by name within a team.

    Attributes:
        team_id: UUID of the team that owns the state.
        name: State name to match, case-insensitively (e.g. `"In Progress"`).
    """

    team_id: str
    name: str


class CommentCreateRequest(LinearModel):
    """Input for adding a comment to an issue.

    Any field accepted by Linear's `CommentCreateInput` may also be passed as an
    extra keyword argument using its camelCase API name.

    Attributes:
        issue_id: UUID of the issue to comment on (required).
        body: Markdown body of the comment (required).
    """

    model_config = ConfigDict(extra="allow")

    issue_id: str
    body: str

    def to_input(self) -> dict[str, Any]:
        """Serialise to a `CommentCreateInput` dict (camelCase, omitting unset values)."""
        return self.model_dump(by_alias=True, exclude_none=True)

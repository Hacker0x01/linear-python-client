"""Typed response models returned by each :class:`~linear_python_client.client.LinearClient` call.

Single-entity queries return a wrapper exposing the entity (e.g.
:class:`IssueResponse.issue`). List queries return a :class:`ConnectionResponse`
subclass exposing `nodes` and `page_info`. Mutations mirror the GraphQL payload,
exposing `success` alongside the affected entity.
"""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import Field

from .entities import (
    Comment,
    Issue,
    IssueDetail,
    IssueLabel,
    LinearModel,
    PageInfo,
    Project,
    Team,
    User,
    WorkflowState,
)


class ConnectionResponse[NodeT](LinearModel):
    """Base for list responses: a page of `nodes` plus its :class:`PageInfo`.

    Iterable and sized, so you can loop over the response directly or read
    `response.nodes` / `response.page_info`.
    """

    nodes: list[NodeT] = Field(default_factory=list)
    page_info: PageInfo = Field(default_factory=PageInfo)

    def __iter__(self) -> Iterator[NodeT]:  # type: ignore[override]
        """Iterate over `nodes`."""
        return iter(self.nodes)

    def __len__(self) -> int:
        """Number of nodes on this page."""
        return len(self.nodes)


# -- single-entity query responses -----------------------------------------


class ViewerResponse(LinearModel):
    """Response for [`viewer`][linear_python_client.client.LinearClient.viewer]."""

    viewer: User | None = None


class UserResponse(LinearModel):
    """Response for [`user`][linear_python_client.client.LinearClient.user]."""

    user: User | None = None


class TeamResponse(LinearModel):
    """Response for [`team`][linear_python_client.client.LinearClient.team]."""

    team: Team | None = None


class IssueResponse(LinearModel):
    """Response for [`issue`][linear_python_client.client.LinearClient.issue]."""

    issue: Issue | None = None


class IssueDetailsResponse(LinearModel):
    """Response for [`issue_details`][linear_python_client.client.LinearClient.issue_details]."""

    issue: IssueDetail | None = None


class WorkflowStateResponse(LinearModel):
    """Resolved workflow state from `find_workflow_state` (`None` if no match)."""

    state: WorkflowState | None = None


class IssueLabelResponse(LinearModel):
    """Resolved issue label from `find_label` (`None` if no match)."""

    label: IssueLabel | None = None


class ProjectResponse(LinearModel):
    """Response for [`project`][linear_python_client.client.LinearClient.project]."""

    project: Project | None = None


class CommentResponse(LinearModel):
    """Response for [`comment`][linear_python_client.client.LinearClient.comment]."""

    comment: Comment | None = None


# -- list query responses ---------------------------------------------------


class UsersResponse(ConnectionResponse[User]):
    """Response for [`users`][linear_python_client.client.LinearClient.users]."""


class TeamsResponse(ConnectionResponse[Team]):
    """Response for [`teams`][linear_python_client.client.LinearClient.teams]."""


class IssuesResponse(ConnectionResponse[Issue]):
    """Response for [`issues`][linear_python_client.client.LinearClient.issues]."""


class ProjectsResponse(ConnectionResponse[Project]):
    """Response for [`projects`][linear_python_client.client.LinearClient.projects]."""


class CommentsResponse(ConnectionResponse[Comment]):
    """Response for [`comments`][linear_python_client.client.LinearClient.comments]."""


class WorkflowStatesResponse(ConnectionResponse[WorkflowState]):
    """[`workflow_states`][linear_python_client.client.LinearClient.workflow_states] response."""


class IssueLabelsResponse(ConnectionResponse[IssueLabel]):
    """Response for [`issue_labels`][linear_python_client.client.LinearClient.issue_labels]."""


# -- mutation responses -----------------------------------------------------


class CreateIssueResponse(LinearModel):
    """Response for [`create_issue`][linear_python_client.client.LinearClient.create_issue]."""

    success: bool = False
    issue: Issue | None = None


class UpdateIssueResponse(LinearModel):
    """Response for [`update_issue`][linear_python_client.client.LinearClient.update_issue]."""

    success: bool = False
    issue: Issue | None = None


class ArchiveIssueResponse(LinearModel):
    """Response for [`archive_issue`][linear_python_client.client.LinearClient.archive_issue]."""

    success: bool = False


class CreateCommentResponse(LinearModel):
    """Response for [`create_comment`][linear_python_client.client.LinearClient.create_comment]."""

    success: bool = False
    comment: Comment | None = None


class AddLabelResponse(LinearModel):
    """Response for [`add_label`][linear_python_client.client.LinearClient.add_label]."""

    success: bool = False
    issue: Issue | None = None


class RemoveLabelResponse(LinearModel):
    """Response for [`remove_label`][linear_python_client.client.LinearClient.remove_label]."""

    success: bool = False
    issue: Issue | None = None

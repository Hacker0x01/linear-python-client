"""A pragmatic synchronous client for the Linear GraphQL API.

Every method takes a single typed request model from `linear_python_client.models.requests`
and returns a dedicated response model from `linear_python_client.models.responses`, so the
input and output of each call are explicit at the type level.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import httpx

from .errors import (
    LinearAuthenticationError,
    LinearGraphQLError,
    LinearNetworkError,
    LinearRateLimitError,
    LinearServerError,
)
from .graphql import queries
from .models.requests import (
    CommentCreateRequest,
    CommentRequest,
    CommentsRequest,
    FindLabelRequest,
    FindProjectRequest,
    FindTeamRequest,
    FindUserRequest,
    FindWorkflowStateRequest,
    IssueAddLabelRequest,
    IssueArchiveRequest,
    IssueCreateRequest,
    IssueLabelsRequest,
    IssueRemoveLabelRequest,
    IssueRequest,
    IssueSetStateRequest,
    IssuesRequest,
    IssueUpdateRequest,
    PaginatedRequest,
    ProjectRequest,
    ProjectsRequest,
    TeamRequest,
    TeamsRequest,
    UserRequest,
    UsersRequest,
    WorkflowStatesRequest,
)
from .models.responses import (
    AddLabelResponse,
    ArchiveIssueResponse,
    CommentResponse,
    CommentsResponse,
    ConnectionResponse,
    CreateCommentResponse,
    CreateIssueResponse,
    IssueDetailsResponse,
    IssueLabelResponse,
    IssueLabelsResponse,
    IssueResponse,
    IssuesResponse,
    ProjectResponse,
    ProjectsResponse,
    RemoveLabelResponse,
    TeamResponse,
    TeamsResponse,
    UpdateIssueResponse,
    UserResponse,
    UsersResponse,
    ViewerResponse,
    WorkflowStateResponse,
    WorkflowStatesResponse,
)

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = "https://api.linear.app/graphql"

RequestT = TypeVar("RequestT", bound=PaginatedRequest)
NodeT = TypeVar("NodeT")


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_node(data: dict[str, Any], key: str) -> dict[str, Any] | None:
    """Return the first node of a connection in ``data[key]``, or ``None``."""
    nodes = (data.get(key) or {}).get("nodes") or []
    return nodes[0] if nodes else None


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value: str) -> bool:
    """Return ``True`` if *value* is a well-formed UUID string."""
    return bool(_UUID_RE.match(value))


def _build_error_message(errors: list[dict[str, Any]]) -> str:
    """Build a human-readable message from a GraphQL ``errors`` list.

    Surfaces per-error codes, Linear's ``userPresentableMessage``, and any
    field-level validation details found in ``extensions.errors``.
    """
    if not errors:
        return "GraphQL error"

    parts: list[str] = []
    for error in errors:
        extensions = error.get("extensions") or {}
        raw_msg = error.get("message") or "GraphQL error"
        code = extensions.get("code") or error.get("code")
        user_msg = extensions.get("userPresentableMessage")
        field_errors: dict[str, Any] = extensions.get("errors") or {}

        # Prefer the user-facing message when it adds information.
        detail = user_msg if (user_msg and user_msg != raw_msg) else raw_msg
        if code:
            detail = f"[{code}] {detail}"
        if field_errors:
            field_parts = []
            for field, msgs in field_errors.items():
                field_msgs = ", ".join(msgs) if isinstance(msgs, list) else str(msgs)
                field_parts.append(f"{field}: {field_msgs}")
            detail = f"{detail} — invalid fields: {'; '.join(field_parts)}"

        parts.append(detail)

    return " | ".join(parts)


class LinearClient:
    """Client for Linear's GraphQL API.

    Authenticate with either a personal API key or an OAuth access token:

    ```python
    client = LinearClient(api_key="lin_api_...")
    client = LinearClient(access_token="...")  # OAuth 2.0 token
    ```

    If neither argument is given, the `LINEAR_API_KEY` environment variable is
    used. The client owns an `httpx.Client` and can be used as a context manager
    to ensure it is closed.
    """

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
        *,
        endpoint: str = DEFAULT_ENDPOINT,
        timeout: float = 30.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        """Create a client.

        Args:
            api_key: A Linear personal API key, sent verbatim in the
                `Authorization` header. Mutually exclusive with `access_token`.
            access_token: An OAuth 2.0 access token, sent as
                `Authorization: Bearer <token>`. Mutually exclusive with `api_key`.
            endpoint: GraphQL endpoint URL. Defaults to the public Linear API.
            timeout: Per-request timeout in seconds for the owned HTTP client.
            http_client: An existing `httpx.Client` to reuse. When supplied, the
                caller retains ownership and `close()` will not close it.

        Raises:
            ValueError: If both or neither credential is provided (and
                `LINEAR_API_KEY` is unset).
        """
        if api_key and access_token:
            raise ValueError("Provide either api_key or access_token, not both.")
        if not api_key and not access_token:
            api_key = os.environ.get("LINEAR_API_KEY")
        if not api_key and not access_token:
            raise ValueError(
                "No credentials supplied. Pass api_key=... or access_token=..., "
                "or set the LINEAR_API_KEY environment variable."
            )

        # Personal API keys are sent verbatim; OAuth tokens use the Bearer scheme.
        authorization = api_key if api_key else f"Bearer {access_token}"
        self.endpoint = endpoint
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)
        self._headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
        }

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close the underlying HTTP client, unless it was supplied by the caller."""
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> LinearClient:
        """Enter a context manager, returning this client."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Exit the context manager and close the HTTP client."""
        self.close()

    # -- core request -------------------------------------------------------

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run a raw GraphQL query or mutation and return its `data` payload.

        This is the escape hatch backing every convenience method; use it
        directly for any operation the typed methods do not cover.

        Args:
            query: The GraphQL document to send.
            variables: Optional variables for the query.

        Returns:
            The `data` object from the response (an empty dict if absent).

        Raises:
            LinearAuthenticationError: The credentials were rejected.
            LinearRateLimitError: A rate limit was exceeded.
            LinearGraphQLError: The API returned one or more GraphQL errors.
            LinearNetworkError: The request never produced a usable response.
        """
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        try:
            response = self._http.post(self.endpoint, json=payload, headers=self._headers)
        except httpx.HTTPError as exc:
            raise LinearNetworkError(f"Request to Linear failed: {exc}") from exc

        # 5xx — server-side failure; surface before attempting JSON parse.
        if response.status_code >= 500:
            preview = response.text[:300].strip() if response.text else "(empty body)"
            msg = f"Linear server error (HTTP {response.status_code}): {preview}"
            logger.error(msg)
            raise LinearServerError(msg, status_code=response.status_code, body_preview=preview)

        # 401/403 at HTTP level — credentials rejected before reaching GraphQL.
        if response.status_code in (401, 403):
            raise LinearAuthenticationError(
                f"Linear rejected the credentials (HTTP {response.status_code})."
            )

        try:
            body = response.json()
        except ValueError as exc:
            preview = response.text[:300].strip() if response.text else "(empty body)"
            raise LinearNetworkError(
                f"Linear returned a non-JSON response (HTTP {response.status_code}): {preview}"
            ) from exc

        errors = body.get("errors")
        data = body.get("data")
        if errors:
            # Partial success: Linear returned 200 with both data and errors.
            # Per the GraphQL spec some fields succeeded; log a warning so callers
            # can inspect which fields failed without the exception swallowing data.
            if data and response.status_code == 200:
                logger.warning(
                    "Linear partial success: response contains both data and errors. "
                    "Raising on the errors; inspect the raw response for partial data. "
                    "errors=%r",
                    errors,
                )
            self._raise_for_errors(errors, response)

        if response.status_code >= 400:
            raise LinearNetworkError(
                f"Linear returned HTTP {response.status_code} with no GraphQL errors."
            )

        return data or {}

    def _raise_for_errors(self, errors: list[dict[str, Any]], response: httpx.Response) -> None:
        """Map a GraphQL ``errors`` list onto the appropriate exception and raise it."""
        code = None
        for error in errors:
            extensions = error.get("extensions") or {}
            code = extensions.get("code") or error.get("code")
            if code:
                break

        message = _build_error_message(errors)

        logger.error(
            "Linear API error: %s",
            message,
            extra={"linear_errors": errors, "http_status": response.status_code},
        )

        if code == "RATELIMITED":
            h = response.headers
            raise LinearRateLimitError(
                message,
                requests_limit=_to_int(h.get("X-RateLimit-Requests-Limit")),
                requests_remaining=_to_int(h.get("X-RateLimit-Requests-Remaining")),
                requests_reset=_to_int(h.get("X-RateLimit-Requests-Reset")),
                complexity_limit=_to_int(h.get("X-RateLimit-Complexity-Limit")),
                complexity_remaining=_to_int(h.get("X-RateLimit-Complexity-Remaining")),
                complexity_reset=_to_int(h.get("X-RateLimit-Complexity-Reset")),
                query_complexity=_to_int(h.get("X-Complexity")),
                endpoint_requests_limit=_to_int(h.get("X-RateLimit-Endpoint-Requests-Limit")),
                endpoint_requests_remaining=_to_int(
                    h.get("X-RateLimit-Endpoint-Requests-Remaining")
                ),
                endpoint_requests_reset=_to_int(h.get("X-RateLimit-Endpoint-Requests-Reset")),
                endpoint_name=h.get("X-RateLimit-Endpoint-Name"),
            )
        if code in ("AUTHENTICATION_ERROR", "UNAUTHENTICATED", "FORBIDDEN"):
            raise LinearAuthenticationError(message)

        raise LinearGraphQLError(message, errors=errors)

    # -- id resolution helpers -----------------------------------------------

    def _lookup_team(self, name_or_key: str) -> str:
        """Resolve a team display name or key to a UUID."""
        resp = self.find_team(FindTeamRequest(name=name_or_key))
        if resp.team is not None and resp.team.id is not None:
            return resp.team.id
        resp = self.find_team(FindTeamRequest(key=name_or_key))
        if resp.team is not None and resp.team.id is not None:
            return resp.team.id
        raise ValueError(f"Team not found: {name_or_key!r}")

    def _lookup_user(self, name_or_email: str) -> str:
        """Resolve a user display name or email address to a UUID."""
        req = (
            FindUserRequest(email=name_or_email)
            if "@" in name_or_email
            else FindUserRequest(name=name_or_email)
        )
        user = self.find_user(req).user
        if user is None or user.id is None:
            raise ValueError(f"User not found: {name_or_email!r}")
        return user.id

    def _lookup_project(self, name: str) -> str:
        """Resolve a project name to a UUID."""
        project = self.find_project(FindProjectRequest(name=name)).project
        if project is None or project.id is None:
            raise ValueError(f"Project not found: {name!r}")
        return project.id

    def _lookup_label(self, name: str, *, team_id: str | None = None) -> str:
        """Resolve a label name to a UUID, optionally scoped to a team."""
        label = self.find_label(FindLabelRequest(name=name, team_id=team_id)).label
        if label is None or label.id is None:
            raise ValueError(f"Label not found: {name!r}")
        return label.id

    def _lookup_workflow_state(self, name: str, team_id: str) -> str:
        """Resolve a workflow state name to a UUID within a team."""
        state = self.find_workflow_state(FindWorkflowStateRequest(team_id=team_id, name=name)).state
        if state is None or state.id is None:
            raise ValueError(f"Workflow state {name!r} not found in team {team_id!r}")
        return state.id

    def _resolve_create_ids(self, request: IssueCreateRequest) -> IssueCreateRequest:
        """Resolve non-UUID strings in *request* to their Linear UUIDs.

        Resolved fields: ``team_id``, ``assignee_id``, ``project_id``,
        ``label_ids``, ``state_id``. UUID values are passed through unchanged.
        """
        updates: dict[str, Any] = {}

        team_id = request.team_id
        if not _is_uuid(team_id):
            team_id = self._lookup_team(team_id)
            updates["team_id"] = team_id

        if request.assignee_id and not _is_uuid(request.assignee_id):
            updates["assignee_id"] = self._lookup_user(request.assignee_id)

        if request.project_id and not _is_uuid(request.project_id):
            updates["project_id"] = self._lookup_project(request.project_id)

        if request.label_ids:
            resolved = [
                label if _is_uuid(label) else self._lookup_label(label, team_id=team_id)
                for label in request.label_ids
            ]
            if resolved != request.label_ids:
                updates["label_ids"] = resolved

        if request.state_id and not _is_uuid(request.state_id):
            updates["state_id"] = self._lookup_workflow_state(request.state_id, team_id)

        return request.model_copy(update=updates) if updates else request

    def _resolve_update_ids(self, request: IssueUpdateRequest) -> IssueUpdateRequest:
        """Resolve non-UUID strings in *request* to their Linear UUIDs.

        Resolved fields: ``assignee_id``, ``project_id``, ``label_ids``.

        Note: ``state_id`` is not resolved here — an update has no team context.
        Use a UUID directly, or call :meth:`find_workflow_state` first.
        """
        updates: dict[str, Any] = {}

        if request.state_id and not _is_uuid(request.state_id):
            raise ValueError(
                "state_id cannot be resolved by name in update_issue (no team context). "
                "Use find_workflow_state() to get the UUID first, or provide a UUID directly."
            )

        if request.assignee_id and not _is_uuid(request.assignee_id):
            updates["assignee_id"] = self._lookup_user(request.assignee_id)

        if request.project_id and not _is_uuid(request.project_id):
            updates["project_id"] = self._lookup_project(request.project_id)

        if request.label_ids:
            resolved = [
                label if _is_uuid(label) else self._lookup_label(label)
                for label in request.label_ids
            ]
            if resolved != request.label_ids:
                updates["label_ids"] = resolved

        return request.model_copy(update=updates) if updates else request

    # -- viewer / users -----------------------------------------------------

    def viewer(self) -> ViewerResponse:
        """Fetch the currently authenticated user.

        Returns:
            A [`ViewerResponse`][linear_python_client.ViewerResponse].
        """
        return ViewerResponse.model_validate(self.execute(queries.VIEWER))

    def user(self, request: UserRequest) -> UserResponse:
        """Fetch a single user by id.

        Args:
            request: A [`UserRequest`][linear_python_client.UserRequest].

        Returns:
            A [`UserResponse`][linear_python_client.UserResponse]; `.user` is
            `None` if not found.
        """
        return UserResponse.model_validate(self.execute(queries.USER, {"id": request.id}))

    def users(self, request: UsersRequest | None = None) -> UsersResponse:
        """List users in the workspace.

        Args:
            request: A [`UsersRequest`][linear_python_client.UsersRequest]. When
                omitted, the first page is returned with no filter.

        Returns:
            A [`UsersResponse`][linear_python_client.UsersResponse].
        """
        request = request or UsersRequest()
        data = self.execute(queries.USERS, request.to_variables())
        return UsersResponse.model_validate(data.get("users") or {})

    # -- teams --------------------------------------------------------------

    def team(self, request: TeamRequest) -> TeamResponse:
        """Fetch a single team by id.

        Args:
            request: A [`TeamRequest`][linear_python_client.TeamRequest].

        Returns:
            A [`TeamResponse`][linear_python_client.TeamResponse]; `.team` is
            `None` if not found.
        """
        return TeamResponse.model_validate(self.execute(queries.TEAM, {"id": request.id}))

    def teams(self, request: TeamsRequest | None = None) -> TeamsResponse:
        """List teams in the workspace.

        Args:
            request: A [`TeamsRequest`][linear_python_client.TeamsRequest]. When
                omitted, the first page is returned with no filter.

        Returns:
            A [`TeamsResponse`][linear_python_client.TeamsResponse].
        """
        request = request or TeamsRequest()
        data = self.execute(queries.TEAMS, request.to_variables())
        return TeamsResponse.model_validate(data.get("teams") or {})

    # -- issues -------------------------------------------------------------

    def issue(self, request: IssueRequest) -> IssueResponse:
        """Fetch a single issue by id or human identifier.

        Args:
            request: An [`IssueRequest`][linear_python_client.IssueRequest].

        Returns:
            An [`IssueResponse`][linear_python_client.IssueResponse]; `.issue`
            is `None` if not found.
        """
        return IssueResponse.model_validate(self.execute(queries.ISSUE, {"id": request.id}))

    def issue_details(self, request: IssueRequest) -> IssueDetailsResponse:
        """Fetch a single issue with its full related data.

        Returns the same core fields as [`issue`][linear_python_client.client.LinearClient.issue]
        plus comments, attachments, project, cycle, parent, sub-issues,
        subscribers, and relations.

        Args:
            request: An [`IssueRequest`][linear_python_client.IssueRequest].

        Returns:
            An [`IssueDetailsResponse`][linear_python_client.IssueDetailsResponse];
            `.issue` is an [`IssueDetail`][linear_python_client.IssueDetail], or
            `None` if not found.
        """
        data = self.execute(queries.ISSUE_DETAILS, {"id": request.id})
        return IssueDetailsResponse.model_validate(data)

    def issues(self, request: IssuesRequest | None = None) -> IssuesResponse:
        """List issues, optionally filtered and ordered.

        Args:
            request: An [`IssuesRequest`][linear_python_client.IssuesRequest].
                When omitted, the first page is returned with no filter.

        Returns:
            An [`IssuesResponse`][linear_python_client.IssuesResponse].
        """
        request = request or IssuesRequest()
        data = self.execute(queries.ISSUES, request.to_variables())
        return IssuesResponse.model_validate(data.get("issues") or {})

    def create_issue(self, request: IssueCreateRequest) -> CreateIssueResponse:
        """Create an issue.

        Args:
            request: An [`IssueCreateRequest`][linear_python_client.IssueCreateRequest].

        Returns:
            A [`CreateIssueResponse`][linear_python_client.CreateIssueResponse]
            exposing `success` and the created `issue`.
        """
        request = self._resolve_create_ids(request)
        data = self.execute(queries.ISSUE_CREATE, {"input": request.to_input()})
        return CreateIssueResponse.model_validate(data.get("issueCreate") or {})

    def update_issue(self, request: IssueUpdateRequest) -> UpdateIssueResponse:
        """Update an issue.

        Args:
            request: An [`IssueUpdateRequest`][linear_python_client.IssueUpdateRequest]
                with `id` and at least one field to change.

        Returns:
            An [`UpdateIssueResponse`][linear_python_client.UpdateIssueResponse]
            exposing `success` and the updated `issue`.

        Raises:
            ValueError: If no fields besides `id` are set.
        """
        request = self._resolve_update_ids(request)
        input_data = request.to_input()
        if not input_data:
            raise ValueError("IssueUpdateRequest requires at least one field to update.")
        data = self.execute(queries.ISSUE_UPDATE, {"id": request.id, "input": input_data})
        return UpdateIssueResponse.model_validate(data.get("issueUpdate") or {})

    def archive_issue(self, request: IssueArchiveRequest) -> ArchiveIssueResponse:
        """Archive an issue.

        Args:
            request: An [`IssueArchiveRequest`][linear_python_client.IssueArchiveRequest].

        Returns:
            An [`ArchiveIssueResponse`][linear_python_client.ArchiveIssueResponse]
            exposing `success`.
        """
        data = self.execute(queries.ISSUE_ARCHIVE, {"id": request.id})
        return ArchiveIssueResponse.model_validate(data.get("issueArchive") or {})

    def add_label(self, request: IssueAddLabelRequest) -> AddLabelResponse:
        """Add a single label to an issue without disturbing its other labels.

        Args:
            request: An [`IssueAddLabelRequest`][linear_python_client.IssueAddLabelRequest].

        Returns:
            An [`AddLabelResponse`][linear_python_client.AddLabelResponse] exposing
            `success` and the updated `issue`.
        """
        data = self.execute(
            queries.ISSUE_ADD_LABEL, {"id": request.id, "labelId": request.label_id}
        )
        return AddLabelResponse.model_validate(data.get("issueAddLabel") or {})

    def remove_label(self, request: IssueRemoveLabelRequest) -> RemoveLabelResponse:
        """Remove a single label from an issue without disturbing its other labels.

        Args:
            request: An [`IssueRemoveLabelRequest`][linear_python_client.IssueRemoveLabelRequest].

        Returns:
            A [`RemoveLabelResponse`][linear_python_client.RemoveLabelResponse]
            exposing `success` and the updated `issue`.
        """
        data = self.execute(
            queries.ISSUE_REMOVE_LABEL, {"id": request.id, "labelId": request.label_id}
        )
        return RemoveLabelResponse.model_validate(data.get("issueRemoveLabel") or {})

    def set_issue_state(self, request: IssueSetStateRequest) -> UpdateIssueResponse:
        """Move an issue to a workflow state (status).

        A focused wrapper over `update_issue` that sets only the state. Resolve a
        state UUID by name with
        [`find_workflow_state`][linear_python_client.client.LinearClient.find_workflow_state].

        Args:
            request: An [`IssueSetStateRequest`][linear_python_client.IssueSetStateRequest].

        Returns:
            An [`UpdateIssueResponse`][linear_python_client.UpdateIssueResponse]
            exposing `success` and the updated `issue`.
        """
        data = self.execute(
            queries.ISSUE_UPDATE, {"id": request.id, "input": {"stateId": request.state_id}}
        )
        return UpdateIssueResponse.model_validate(data.get("issueUpdate") or {})

    # -- projects -----------------------------------------------------------

    def project(self, request: ProjectRequest) -> ProjectResponse:
        """Fetch a single project by id.

        Args:
            request: A [`ProjectRequest`][linear_python_client.ProjectRequest].

        Returns:
            A [`ProjectResponse`][linear_python_client.ProjectResponse];
            `.project` is `None` if not found.
        """
        return ProjectResponse.model_validate(self.execute(queries.PROJECT, {"id": request.id}))

    def projects(self, request: ProjectsRequest | None = None) -> ProjectsResponse:
        """List projects in the workspace.

        Args:
            request: A [`ProjectsRequest`][linear_python_client.ProjectsRequest].
                When omitted, the first page is returned with no filter.

        Returns:
            A [`ProjectsResponse`][linear_python_client.ProjectsResponse].
        """
        request = request or ProjectsRequest()
        data = self.execute(queries.PROJECTS, request.to_variables())
        return ProjectsResponse.model_validate(data.get("projects") or {})

    # -- comments -----------------------------------------------------------

    def comment(self, request: CommentRequest) -> CommentResponse:
        """Fetch a single comment by id.

        Args:
            request: A [`CommentRequest`][linear_python_client.CommentRequest].

        Returns:
            A [`CommentResponse`][linear_python_client.CommentResponse];
            `.comment` is `None` if not found.
        """
        return CommentResponse.model_validate(self.execute(queries.COMMENT, {"id": request.id}))

    def comments(self, request: CommentsRequest | None = None) -> CommentsResponse:
        """List comments, optionally scoped to a single issue.

        Args:
            request: A [`CommentsRequest`][linear_python_client.CommentsRequest].
                Set `issue_id` to scope to one issue. When omitted, the first page
                is returned with no filter.

        Returns:
            A [`CommentsResponse`][linear_python_client.CommentsResponse].
        """
        request = request or CommentsRequest()
        variables = request.to_variables()
        if request.issue_id:
            issue_filter = {"issue": {"id": {"eq": request.issue_id}}}
            existing = variables.get("filter")
            variables["filter"] = {**issue_filter, **existing} if existing else issue_filter
        data = self.execute(queries.COMMENTS, variables)
        return CommentsResponse.model_validate(data.get("comments") or {})

    def create_comment(self, request: CommentCreateRequest) -> CreateCommentResponse:
        """Add a comment to an issue.

        Args:
            request: A [`CommentCreateRequest`][linear_python_client.CommentCreateRequest].

        Returns:
            A [`CreateCommentResponse`][linear_python_client.CreateCommentResponse]
            exposing `success` and the created `comment`.
        """
        data = self.execute(queries.COMMENT_CREATE, {"input": request.to_input()})
        return CreateCommentResponse.model_validate(data.get("commentCreate") or {})

    # -- workflow states / labels ------------------------------------------

    def workflow_states(
        self, request: WorkflowStatesRequest | None = None
    ) -> WorkflowStatesResponse:
        """List workflow states, optionally scoped to a single team.

        Args:
            request: A [`WorkflowStatesRequest`][linear_python_client.WorkflowStatesRequest].
                Set `team_id` to scope to one team. When omitted, the first page is
                returned with no filter.

        Returns:
            A [`WorkflowStatesResponse`][linear_python_client.WorkflowStatesResponse].
        """
        request = request or WorkflowStatesRequest()
        variables = request.to_variables()
        if request.team_id:
            team_filter = {"team": {"id": {"eq": request.team_id}}}
            existing = variables.get("filter")
            variables["filter"] = {**team_filter, **existing} if existing else team_filter
        data = self.execute(queries.WORKFLOW_STATES, variables)
        return WorkflowStatesResponse.model_validate(data.get("workflowStates") or {})

    def find_workflow_state(self, request: FindWorkflowStateRequest) -> WorkflowStateResponse:
        """Resolve a workflow state by name within a team.

        Useful for turning a human status name (e.g. `"In Progress"`) into the
        UUID that [`set_issue_state`][linear_python_client.client.LinearClient.set_issue_state]
        expects. Matching is case-insensitive.

        Args:
            request: A [`FindWorkflowStateRequest`][linear_python_client.FindWorkflowStateRequest].

        Returns:
            A [`WorkflowStateResponse`][linear_python_client.WorkflowStateResponse];
            `.state` is `None` if no state matches.
        """
        filter_ = {
            "team": {"id": {"eq": request.team_id}},
            "name": {"eqIgnoreCase": request.name},
        }
        data = self.execute(queries.WORKFLOW_STATES, {"first": 1, "filter": filter_})
        return WorkflowStateResponse.model_validate({"state": _first_node(data, "workflowStates")})

    def find_team(self, request: FindTeamRequest) -> TeamResponse:
        """Resolve a team by display name or key.

        Args:
            request: A [`FindTeamRequest`][linear_python_client.FindTeamRequest]
                with `name` and/or `key`.

        Returns:
            A [`TeamResponse`][linear_python_client.TeamResponse]; `.team` is
            `None` if no team matches.
        """
        data = self.execute(queries.TEAMS, {"first": 1, "filter": request.to_filter()})
        return TeamResponse.model_validate({"team": _first_node(data, "teams")})

    def find_user(self, request: FindUserRequest) -> UserResponse:
        """Resolve a user by name, display name, or email.

        Args:
            request: A [`FindUserRequest`][linear_python_client.FindUserRequest]
                with `name` and/or `email`.

        Returns:
            A [`UserResponse`][linear_python_client.UserResponse]; `.user` is
            `None` if no user matches.
        """
        data = self.execute(queries.USERS, {"first": 1, "filter": request.to_filter()})
        return UserResponse.model_validate({"user": _first_node(data, "users")})

    def find_project(self, request: FindProjectRequest) -> ProjectResponse:
        """Resolve a project by name (case-insensitive).

        Args:
            request: A [`FindProjectRequest`][linear_python_client.FindProjectRequest].

        Returns:
            A [`ProjectResponse`][linear_python_client.ProjectResponse]; `.project`
            is `None` if no project matches.
        """
        data = self.execute(queries.PROJECTS, {"first": 1, "filter": request.to_filter()})
        return ProjectResponse.model_validate({"project": _first_node(data, "projects")})

    def find_label(self, request: FindLabelRequest) -> IssueLabelResponse:
        """Resolve an issue label by name, optionally scoped to a team.

        Args:
            request: A [`FindLabelRequest`][linear_python_client.FindLabelRequest].

        Returns:
            An [`IssueLabelResponse`][linear_python_client.IssueLabelResponse];
            `.label` is `None` if no label matches.
        """
        data = self.execute(queries.ISSUE_LABELS, {"first": 1, "filter": request.to_filter()})
        return IssueLabelResponse.model_validate({"label": _first_node(data, "issueLabels")})

    def issue_labels(self, request: IssueLabelsRequest | None = None) -> IssueLabelsResponse:
        """List issue labels in the workspace.

        Args:
            request: An [`IssueLabelsRequest`][linear_python_client.IssueLabelsRequest].
                When omitted, the first page is returned with no filter.

        Returns:
            An [`IssueLabelsResponse`][linear_python_client.IssueLabelsResponse].
        """
        request = request or IssueLabelsRequest()
        data = self.execute(queries.ISSUE_LABELS, request.to_variables())
        return IssueLabelsResponse.model_validate(data.get("issueLabels") or {})

    # -- pagination ---------------------------------------------------------

    def paginate(
        self,
        method: Callable[[RequestT], ConnectionResponse[NodeT]],
        request: RequestT,
        *,
        page_size: int | None = None,
    ) -> Iterator[NodeT]:
        """Yield every node across all pages of a list method.

        Transparently follows the cursor (`page_info.end_cursor`) until
        `has_next_page` is false, so you can iterate an entire result set without
        managing pagination yourself:

        ```python
        from linear_python_client import IssuesRequest

        for issue in client.paginate(client.issues, IssuesRequest(filter={...})):
            print(issue.identifier, issue.title)
        ```

        Args:
            method: A list method on this client (e.g. `client.issues`,
                `client.teams`, `client.projects`).
            request: The request to start from. It is copied; `after` is advanced
                automatically each page.
            page_size: Results to request per page, set as `first`. Leave unset to
                use Linear's default of 50.

        Yields:
            Each node from every page, in order.
        """
        current = request.model_copy(deep=True)
        if page_size is not None:
            current.first = page_size
        while True:
            response = method(current)
            yield from response.nodes
            page = response.page_info
            if not page.has_next_page or not page.end_cursor:
                break
            current = current.model_copy(update={"after": page.end_cursor})

"""A pragmatic synchronous client for the Linear GraphQL API.

Every method takes a single typed request model from `linear_python.models.requests`
and returns a dedicated response model from `linear_python.models.responses`, so the
input and output of each call are explicit at the type level.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from typing import Any, TypeVar

import httpx

from .errors import (
    LinearAuthenticationError,
    LinearGraphQLError,
    LinearNetworkError,
    LinearRateLimitError,
)
from .graphql import queries
from .models.requests import (
    CommentCreateRequest,
    CommentRequest,
    CommentsRequest,
    IssueArchiveRequest,
    IssueCreateRequest,
    IssueLabelsRequest,
    IssueRequest,
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
    ArchiveIssueResponse,
    CommentResponse,
    CommentsResponse,
    ConnectionResponse,
    CreateCommentResponse,
    CreateIssueResponse,
    IssueLabelsResponse,
    IssueResponse,
    IssuesResponse,
    ProjectResponse,
    ProjectsResponse,
    TeamResponse,
    TeamsResponse,
    UpdateIssueResponse,
    UserResponse,
    UsersResponse,
    ViewerResponse,
    WorkflowStatesResponse,
)

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

        if response.status_code in (401, 403):
            raise LinearAuthenticationError(
                f"Linear rejected the credentials (HTTP {response.status_code})."
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise LinearNetworkError(
                f"Linear returned a non-JSON response (HTTP {response.status_code})."
            ) from exc

        errors = body.get("errors")
        if errors:
            self._raise_for_errors(errors, response)

        if response.status_code >= 400:
            raise LinearNetworkError(
                f"Linear returned HTTP {response.status_code} with no GraphQL errors."
            )

        return body.get("data") or {}

    def _raise_for_errors(self, errors: list[dict[str, Any]], response: httpx.Response) -> None:
        """Map a GraphQL ``errors`` list onto the appropriate exception and raise it."""
        code = None
        for error in errors:
            extensions = error.get("extensions") or {}
            code = extensions.get("code") or error.get("code")
            if code:
                break

        message = errors[0].get("message", "GraphQL error") if errors else "GraphQL error"

        if code == "RATELIMITED":
            headers = response.headers
            raise LinearRateLimitError(
                message,
                requests_limit=_to_int(headers.get("X-RateLimit-Requests-Limit")),
                requests_remaining=_to_int(headers.get("X-RateLimit-Requests-Remaining")),
                requests_reset=_to_int(headers.get("X-RateLimit-Requests-Reset")),
                complexity_limit=_to_int(headers.get("X-RateLimit-Complexity-Limit")),
                complexity_remaining=_to_int(headers.get("X-RateLimit-Complexity-Remaining")),
                complexity_reset=_to_int(headers.get("X-RateLimit-Complexity-Reset")),
            )
        if code in ("AUTHENTICATION_ERROR", "FORBIDDEN"):
            raise LinearAuthenticationError(message)

        raise LinearGraphQLError(message, errors=errors)

    # -- viewer / users -----------------------------------------------------

    def viewer(self) -> ViewerResponse:
        """Fetch the currently authenticated user.

        Returns:
            A [`ViewerResponse`][linear_python.ViewerResponse].
        """
        return ViewerResponse.model_validate(self.execute(queries.VIEWER))

    def user(self, request: UserRequest) -> UserResponse:
        """Fetch a single user by id.

        Args:
            request: A [`UserRequest`][linear_python.UserRequest].

        Returns:
            A [`UserResponse`][linear_python.UserResponse]; `.user` is
            `None` if not found.
        """
        return UserResponse.model_validate(self.execute(queries.USER, {"id": request.id}))

    def users(self, request: UsersRequest | None = None) -> UsersResponse:
        """List users in the workspace.

        Args:
            request: A [`UsersRequest`][linear_python.UsersRequest]. When
                omitted, the first page is returned with no filter.

        Returns:
            A [`UsersResponse`][linear_python.UsersResponse].
        """
        request = request or UsersRequest()
        data = self.execute(queries.USERS, request.to_variables())
        return UsersResponse.model_validate(data.get("users") or {})

    # -- teams --------------------------------------------------------------

    def team(self, request: TeamRequest) -> TeamResponse:
        """Fetch a single team by id.

        Args:
            request: A [`TeamRequest`][linear_python.TeamRequest].

        Returns:
            A [`TeamResponse`][linear_python.TeamResponse]; `.team` is
            `None` if not found.
        """
        return TeamResponse.model_validate(self.execute(queries.TEAM, {"id": request.id}))

    def teams(self, request: TeamsRequest | None = None) -> TeamsResponse:
        """List teams in the workspace.

        Args:
            request: A [`TeamsRequest`][linear_python.TeamsRequest]. When
                omitted, the first page is returned with no filter.

        Returns:
            A [`TeamsResponse`][linear_python.TeamsResponse].
        """
        request = request or TeamsRequest()
        data = self.execute(queries.TEAMS, request.to_variables())
        return TeamsResponse.model_validate(data.get("teams") or {})

    # -- issues -------------------------------------------------------------

    def issue(self, request: IssueRequest) -> IssueResponse:
        """Fetch a single issue by id or human identifier.

        Args:
            request: An [`IssueRequest`][linear_python.IssueRequest].

        Returns:
            An [`IssueResponse`][linear_python.IssueResponse]; `.issue`
            is `None` if not found.
        """
        return IssueResponse.model_validate(self.execute(queries.ISSUE, {"id": request.id}))

    def issues(self, request: IssuesRequest | None = None) -> IssuesResponse:
        """List issues, optionally filtered and ordered.

        Args:
            request: An [`IssuesRequest`][linear_python.IssuesRequest].
                When omitted, the first page is returned with no filter.

        Returns:
            An [`IssuesResponse`][linear_python.IssuesResponse].
        """
        request = request or IssuesRequest()
        data = self.execute(queries.ISSUES, request.to_variables())
        return IssuesResponse.model_validate(data.get("issues") or {})

    def create_issue(self, request: IssueCreateRequest) -> CreateIssueResponse:
        """Create an issue.

        Args:
            request: An [`IssueCreateRequest`][linear_python.IssueCreateRequest].

        Returns:
            A [`CreateIssueResponse`][linear_python.CreateIssueResponse]
            exposing `success` and the created `issue`.
        """
        data = self.execute(queries.ISSUE_CREATE, {"input": request.to_input()})
        return CreateIssueResponse.model_validate(data.get("issueCreate") or {})

    def update_issue(self, request: IssueUpdateRequest) -> UpdateIssueResponse:
        """Update an issue.

        Args:
            request: An [`IssueUpdateRequest`][linear_python.IssueUpdateRequest]
                with `id` and at least one field to change.

        Returns:
            An [`UpdateIssueResponse`][linear_python.UpdateIssueResponse]
            exposing `success` and the updated `issue`.

        Raises:
            ValueError: If no fields besides `id` are set.
        """
        input_data = request.to_input()
        if not input_data:
            raise ValueError("IssueUpdateRequest requires at least one field to update.")
        data = self.execute(queries.ISSUE_UPDATE, {"id": request.id, "input": input_data})
        return UpdateIssueResponse.model_validate(data.get("issueUpdate") or {})

    def archive_issue(self, request: IssueArchiveRequest) -> ArchiveIssueResponse:
        """Archive an issue.

        Args:
            request: An [`IssueArchiveRequest`][linear_python.IssueArchiveRequest].

        Returns:
            An [`ArchiveIssueResponse`][linear_python.ArchiveIssueResponse]
            exposing `success`.
        """
        data = self.execute(queries.ISSUE_ARCHIVE, {"id": request.id})
        return ArchiveIssueResponse.model_validate(data.get("issueArchive") or {})

    # -- projects -----------------------------------------------------------

    def project(self, request: ProjectRequest) -> ProjectResponse:
        """Fetch a single project by id.

        Args:
            request: A [`ProjectRequest`][linear_python.ProjectRequest].

        Returns:
            A [`ProjectResponse`][linear_python.ProjectResponse];
            `.project` is `None` if not found.
        """
        return ProjectResponse.model_validate(self.execute(queries.PROJECT, {"id": request.id}))

    def projects(self, request: ProjectsRequest | None = None) -> ProjectsResponse:
        """List projects in the workspace.

        Args:
            request: A [`ProjectsRequest`][linear_python.ProjectsRequest].
                When omitted, the first page is returned with no filter.

        Returns:
            A [`ProjectsResponse`][linear_python.ProjectsResponse].
        """
        request = request or ProjectsRequest()
        data = self.execute(queries.PROJECTS, request.to_variables())
        return ProjectsResponse.model_validate(data.get("projects") or {})

    # -- comments -----------------------------------------------------------

    def comment(self, request: CommentRequest) -> CommentResponse:
        """Fetch a single comment by id.

        Args:
            request: A [`CommentRequest`][linear_python.CommentRequest].

        Returns:
            A [`CommentResponse`][linear_python.CommentResponse];
            `.comment` is `None` if not found.
        """
        return CommentResponse.model_validate(self.execute(queries.COMMENT, {"id": request.id}))

    def comments(self, request: CommentsRequest | None = None) -> CommentsResponse:
        """List comments, optionally scoped to a single issue.

        Args:
            request: A [`CommentsRequest`][linear_python.CommentsRequest].
                Set `issue_id` to scope to one issue. When omitted, the first page
                is returned with no filter.

        Returns:
            A [`CommentsResponse`][linear_python.CommentsResponse].
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
            request: A [`CommentCreateRequest`][linear_python.CommentCreateRequest].

        Returns:
            A [`CreateCommentResponse`][linear_python.CreateCommentResponse]
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
            request: A [`WorkflowStatesRequest`][linear_python.WorkflowStatesRequest].
                Set `team_id` to scope to one team. When omitted, the first page is
                returned with no filter.

        Returns:
            A [`WorkflowStatesResponse`][linear_python.WorkflowStatesResponse].
        """
        request = request or WorkflowStatesRequest()
        variables = request.to_variables()
        if request.team_id:
            team_filter = {"team": {"id": {"eq": request.team_id}}}
            existing = variables.get("filter")
            variables["filter"] = {**team_filter, **existing} if existing else team_filter
        data = self.execute(queries.WORKFLOW_STATES, variables)
        return WorkflowStatesResponse.model_validate(data.get("workflowStates") or {})

    def issue_labels(self, request: IssueLabelsRequest | None = None) -> IssueLabelsResponse:
        """List issue labels in the workspace.

        Args:
            request: An [`IssueLabelsRequest`][linear_python.IssueLabelsRequest].
                When omitted, the first page is returned with no filter.

        Returns:
            An [`IssueLabelsResponse`][linear_python.IssueLabelsResponse].
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
        from linear_python import IssuesRequest

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

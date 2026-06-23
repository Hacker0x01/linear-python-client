# linear-python-client

A small, pragmatic synchronous Python client for the [Linear](https://linear.app)
GraphQL API. Linear's official SDK is TypeScript-only — this package gives Python
the same ergonomics, built on [Pydantic](https://docs.pydantic.dev/): every call
takes a typed **`*Request`** model and returns a dedicated **`*Response`** model, so
inputs and outputs are explicit and validated. A generic `execute()` escape hatch
covers anything the typed methods don't.

Built against the [Linear developer docs](https://linear.app/developers).

📖 **Full documentation:** <https://hacker0x01.github.io/linear-python-client/>

## Installation

```sh
uv add linear-python-client
# or
pip install linear-python-client
```

Or for local development of this repo:

```sh
uv sync
```

Requires Python 3.13+.

## Authentication

The client accepts either a personal API key or an OAuth 2.0 access token.

```python
from linear_python_client import LinearClient

# Personal API key (sent as the raw `Authorization` header value)
client = LinearClient(api_key="lin_api_...")

# OAuth 2.0 access token (sent as `Authorization: Bearer <token>`)
client = LinearClient(access_token="...")

# Or set LINEAR_API_KEY in the environment and call LinearClient()
client = LinearClient()
```

Use it as a context manager to close the underlying HTTP client automatically:

```python
with LinearClient() as client:
    print(client.viewer().viewer.name)
```

## Quickstart

Each method takes a `*Request` and returns a `*Response`:

```python
from linear_python_client import (
    LinearClient,
    IssueRequest,
    IssueCreateRequest,
    IssueUpdateRequest,
    IssueArchiveRequest,
    CommentCreateRequest,
)

with LinearClient() as client:
    # The authenticated user
    me = client.viewer().viewer
    print(me.name, me.email)

    # Fetch a single issue by id or identifier
    issue = client.issue(IssueRequest(id="ENG-123")).issue
    print(issue.title, issue.state.name)

    # Create an issue
    created = client.create_issue(
        IssueCreateRequest(
            team_id="9cfb482a-81e3-4154-b5b9-2c805e70a02d",
            title="New exception",
            description="More detailed error report in **markdown**",
            priority=2,
        )
    )
    print(created.success, created.issue.identifier)

    # Update it
    client.update_issue(IssueUpdateRequest(id=created.issue.id, title="Renamed", priority=1))

    # Comment on it
    client.create_comment(CommentCreateRequest(issue_id=created.issue.id, body="On it 👍"))

    # Archive it
    client.archive_issue(IssueArchiveRequest(id=created.issue.id))
```

Field names are Pythonic snake_case with camelCase aliases, so `IssueCreateRequest`
accepts `team_id=` (or `teamId=`) and the parsed models expose `issue.created_at`,
`issue.assignee.display_name`, and so on.

## Listing, filtering & pagination

List methods take a `*Request` (with `first`, `after`, and a `filter` dict that maps
directly to Linear's [filtering syntax](https://linear.app/developers/filtering)) and
return a `*Response` that holds `.nodes` and `.page_info` (and is iterable).

```python
from linear_python_client import IssuesRequest

# First 20 high-priority issues assigned to a specific user
resp = client.issues(
    IssuesRequest(
        first=20,
        filter={
            "priority": {"eq": 1},
            "assignee": {"email": {"eq": "you@example.com"}},
        },
        order_by="updatedAt",
    )
)
for issue in resp.nodes:
    print(issue.identifier, issue.title)

print(resp.page_info.has_next_page, resp.page_info.end_cursor)
```

Use `paginate()` to transparently follow the cursor across every page. Pass the list
method and a starting request:

```python
for issue in client.paginate(client.issues, IssuesRequest(filter={"state": {"type": {"eq": "started"}}})):
    print(issue.identifier, issue.title)
```

`paginate()` works with any list method (`client.issues`, `client.teams`,
`client.projects`, `client.comments`, `client.users`, …) and its matching request.

## Labels, status & full details

```python
from linear_python_client import (
    IssueAddLabelRequest,
    IssueRemoveLabelRequest,
    IssueSetStateRequest,
    FindWorkflowStateRequest,
    IssueRequest,
)

# Add / remove a single label without disturbing the issue's other labels
client.add_label(IssueAddLabelRequest(id=issue_id, label_id=label_id))
client.remove_label(IssueRemoveLabelRequest(id=issue_id, label_id=label_id))

# Update status: resolve a state by name, then set it
state = client.find_workflow_state(FindWorkflowStateRequest(team_id=team_id, name="In Progress")).state
client.set_issue_state(IssueSetStateRequest(id=issue_id, state_id=state.id))

# Full details: comments, attachments, project, cycle, parent, sub-issues, subscribers, relations
detail = client.issue_details(IssueRequest(id="ENG-123")).issue
print(detail.state.name, len(detail.comments), len(detail.attachments))
for child in detail.children:
    print("sub-issue:", child.identifier, child.title)
```

## Looking things up by name (instead of UUIDs)

Most calls take UUIDs. Use the `find_*` resolvers to turn a human name/key/email into
the entity (and its `.id`) first:

```python
from linear_python_client import (
    FindTeamRequest, FindUserRequest, FindProjectRequest, FindLabelRequest,
    IssueCreateRequest,
)

team = client.find_team(FindTeamRequest(key="RAV")).team        # or name="Ravens"
assignee = client.find_user(FindUserRequest(name="Elijah Winter")).user  # or email=...
bug = client.find_label(FindLabelRequest(name="bug", team_id=team.id)).label

client.create_issue(IssueCreateRequest(
    team_id=team.id,
    title="New issue",
    assignee_id=assignee.id,
    label_ids=[bug.id],
))
```

Each resolver returns the matching entity, or `None` if nothing matches. Name matching
is case-insensitive; team `key` is matched exactly. `find_workflow_state` (for statuses)
works the same way.

## Escape hatch: raw GraphQL

Anything not covered by a convenience method can be run directly. `execute()`
returns the `data` object and raises on errors.

```python
data = client.execute(
    """
    query($id: String!) {
      issue(id: $id) { id title attachments { nodes { url title } } }
    }
    """,
    {"id": "ENG-123"},
)
print(data["issue"]["attachments"]["nodes"])
```

## Errors

All exceptions subclass `LinearError`:

| Exception | Raised when |
|-----------|-------------|
| `LinearAuthenticationError` | Credentials are rejected (HTTP 401/403 or auth error code) |
| `LinearRateLimitError` | A rate limit is hit (`RATELIMITED`); carries the `X-RateLimit-*` header values |
| `LinearGraphQLError` | The API returns GraphQL `errors`; exposes `.errors` and `.code` |
| `LinearNetworkError` | The request never produced a usable response |

```python
from linear_python_client import LinearClient, LinearRateLimitError, IssuesRequest

try:
    client.issues(IssuesRequest(first=100))
except LinearRateLimitError as exc:
    print("Rate limited; resets at", exc.requests_reset)
```

## Available client methods

Each method maps a `*Request` to a `*Response`:

| Method | Request | Response |
|--------|---------|----------|
| `viewer()` | – | `ViewerResponse` |
| `user(...)` | `UserRequest` | `UserResponse` |
| `users(...)` | `UsersRequest` | `UsersResponse` |
| `team(...)` | `TeamRequest` | `TeamResponse` |
| `teams(...)` | `TeamsRequest` | `TeamsResponse` |
| `issue(...)` | `IssueRequest` | `IssueResponse` |
| `issue_details(...)` | `IssueRequest` | `IssueDetailsResponse` |
| `issues(...)` | `IssuesRequest` | `IssuesResponse` |
| `create_issue(...)` | `IssueCreateRequest` | `CreateIssueResponse` |
| `update_issue(...)` | `IssueUpdateRequest` | `UpdateIssueResponse` |
| `archive_issue(...)` | `IssueArchiveRequest` | `ArchiveIssueResponse` |
| `add_label(...)` | `IssueAddLabelRequest` | `AddLabelResponse` |
| `remove_label(...)` | `IssueRemoveLabelRequest` | `RemoveLabelResponse` |
| `set_issue_state(...)` | `IssueSetStateRequest` | `UpdateIssueResponse` |
| `project(...)` | `ProjectRequest` | `ProjectResponse` |
| `projects(...)` | `ProjectsRequest` | `ProjectsResponse` |
| `comment(...)` | `CommentRequest` | `CommentResponse` |
| `comments(...)` | `CommentsRequest` | `CommentsResponse` |
| `create_comment(...)` | `CommentCreateRequest` | `CreateCommentResponse` |
| `workflow_states(...)` | `WorkflowStatesRequest` | `WorkflowStatesResponse` |
| `issue_labels(...)` | `IssueLabelsRequest` | `IssueLabelsResponse` |
| `find_team(...)` | `FindTeamRequest` | `TeamResponse` |
| `find_user(...)` | `FindUserRequest` | `UserResponse` |
| `find_project(...)` | `FindProjectRequest` | `ProjectResponse` |
| `find_label(...)` | `FindLabelRequest` | `IssueLabelResponse` |
| `find_workflow_state(...)` | `FindWorkflowStateRequest` | `WorkflowStateResponse` |
| `execute(query, variables)` | – | `dict` |
| `paginate(method, request)` | a `*Request` | iterator of nodes |

List requests are optional (e.g. `client.issues()` returns the first page unfiltered).

## Development

```sh
uv sync          # install deps + dev tools
uv run pytest    # run the mocked unit tests with coverage (no network)
uv run ruff check
```

The test suite mocks the GraphQL endpoint, so no credentials or network access are
needed. An optional live smoke test runs only when `LINEAR_API_KEY` is set.

`pytest` runs with coverage by default and **fails under 90%** (configured in
`pyproject.toml`); the suite currently covers ~99% of the package. A coverage summary
prints after each run — add `--cov-report=html` for an annotated HTML report in
`htmlcov/`.

### Live smoke test

`scripts/smoke_test.py` exercises **every** client method against the real Linear API
and, after each mutation, re-pulls the issue to confirm the change landed (create →
update → set status → add/remove label → comment → full details). It creates one
clearly-labelled test issue and archives it at the end, so it cleans up after itself.

```sh
LINEAR_API_KEY=lin_api_... uv run python scripts/smoke_test.py
# optionally pin the team (defaults to the first one):
LINEAR_API_KEY=... LINEAR_TEAM_ID=<uuid> uv run python scripts/smoke_test.py
```

It prints a ✓/✗ per check and exits non-zero if any fail. Because it writes to your
workspace, it's a manual script — it is not part of `pytest`.

### Building & releasing

Build the distributions locally with uv:

```sh
uv build              # writes sdist + wheel to ./dist
uvx twine check dist/*  # validate metadata / README rendering
```

Releases are automated by [`.github/workflows/publish.yml`](.github/workflows/publish.yml).
On every push and PR it lints, tests (with the coverage gate), builds the sdist + wheel,
validates the metadata, and smoke-tests that the wheel installs and imports. When a
**GitHub Release is published**, it additionally publishes the build to PyPI — after
which `pip install linear-python-client` and `uv add linear-python-client` work.

Publishing uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/)
(OIDC), so no API token or secret is stored. One-time setup:

1. On PyPI, add a trusted publisher for the project pointing at this repo, workflow
   `publish.yml`, and environment `pypi`.
2. In the repo, create a `pypi` [environment](https://docs.github.com/actions/deployment/targeting-different-environments/using-environments-for-deployment)
   (Settings → Environments).

To cut a release: bump `version` in `pyproject.toml`, then create a matching GitHub
Release (e.g. tag `v0.1.1`) — the workflow builds and uploads it to PyPI.

> [!NOTE]
> `requires-python` is `>=3.13`, so installs require Python 3.13+.

### Documentation

The docs are built with [MkDocs](https://www.mkdocs.org/) +
[Material](https://squidfunk.github.io/mkdocs-material/) and the API reference is
generated automatically from docstrings via
[mkdocstrings](https://mkdocstrings.github.io/).

```sh
uv run --group docs mkdocs serve          # live preview at http://127.0.0.1:8000
uv run --group docs mkdocs build --strict # production build into ./site
```

They deploy to GitHub Pages automatically on every push to `main` via
[`.github/workflows/docs.yml`](.github/workflows/docs.yml). To enable publishing,
set **Settings → Pages → Build and deployment → Source** to **GitHub Actions** in the
repository once. Update the `site_url`/`repo_url` in `mkdocs.yml` if the repo lives
under a different owner.

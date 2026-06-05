# linear-python

A small, pragmatic synchronous Python client for the [Linear](https://linear.app)
GraphQL API. Linear's official SDK is TypeScript-only — this package gives Python
the same ergonomics, built on [Pydantic](https://docs.pydantic.dev/): every call
takes a typed **`*Request`** model and returns a dedicated **`*Response`** model, so
inputs and outputs are explicit and validated. A generic `execute()` escape hatch
covers anything the typed methods don't.

Built against the [Linear developer docs](https://linear.app/developers).

📖 **Full documentation:** <https://ewinter-hackerone.github.io/linear-python/>

## Installation

The package is distributed as assets on its [GitHub Releases](https://github.com/ewinter-hackerone/linear-python/releases)
(not on PyPI). Install the wheel from a release, or straight from a tag:

```sh
# from a release wheel
uv pip install https://github.com/ewinter-hackerone/linear-python/releases/download/v0.1.0/linear_python-0.1.0-py3-none-any.whl

# or from a tag (builds from source)
uv pip install "git+https://github.com/ewinter-hackerone/linear-python@v0.1.0"
```

Or for local development of this repo:

```sh
uv sync
```

Requires Python 3.14+.

## Authentication

The client accepts either a personal API key or an OAuth 2.0 access token.

```python
from linear_python import LinearClient

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
from linear_python import (
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
from linear_python import IssuesRequest

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
from linear_python import LinearClient, LinearRateLimitError, IssuesRequest

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
| `issues(...)` | `IssuesRequest` | `IssuesResponse` |
| `create_issue(...)` | `IssueCreateRequest` | `CreateIssueResponse` |
| `update_issue(...)` | `IssueUpdateRequest` | `UpdateIssueResponse` |
| `archive_issue(...)` | `IssueArchiveRequest` | `ArchiveIssueResponse` |
| `project(...)` | `ProjectRequest` | `ProjectResponse` |
| `projects(...)` | `ProjectsRequest` | `ProjectsResponse` |
| `comment(...)` | `CommentRequest` | `CommentResponse` |
| `comments(...)` | `CommentsRequest` | `CommentsResponse` |
| `create_comment(...)` | `CommentCreateRequest` | `CreateCommentResponse` |
| `workflow_states(...)` | `WorkflowStatesRequest` | `WorkflowStatesResponse` |
| `issue_labels(...)` | `IssueLabelsRequest` | `IssueLabelsResponse` |
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

### Building & releasing

Build the distributions locally with uv:

```sh
uv build              # writes sdist + wheel to ./dist
uvx twine check dist/*  # validate metadata / README rendering
```

Releases are automated by [`.github/workflows/publish.yml`](.github/workflows/publish.yml).
On every push and PR it lints, tests (with the coverage gate), builds the sdist + wheel,
validates the metadata, and smoke-tests that the wheel installs and imports. When a
**GitHub Release is published**, it additionally attaches the built sdist + wheel as
assets on that release.

To cut a release: bump `version` in `pyproject.toml`, then create a matching GitHub
Release (e.g. tag `v0.1.0`). The workflow uploads `linear_python-<version>.tar.gz` and
`linear_python-<version>-py3-none-any.whl` to the release.

Install from a release asset (the package is not published to PyPI):

```sh
# wheel
uv pip install https://github.com/ewinter-hackerone/linear-python/releases/download/v0.1.0/linear_python-0.1.0-py3-none-any.whl
pip install https://github.com/ewinter-hackerone/linear-python/releases/download/v0.1.0/linear_python-0.1.0-py3-none-any.whl

# or straight from a tag (builds from source)
uv pip install "git+https://github.com/ewinter-hackerone/linear-python@v0.1.0"
```

> [!NOTE]
> `requires-python` is `>=3.14`, so installs require Python 3.14+.

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

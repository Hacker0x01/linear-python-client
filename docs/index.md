# linear-python

A small, pragmatic **synchronous Python client** for the [Linear](https://linear.app)
GraphQL API. Linear's official SDK is TypeScript-only — this package gives Python the
same ergonomics, built on [Pydantic](https://docs.pydantic.dev/): every call takes a
typed **`*Request`** model and returns a dedicated **`*Response`** model, plus a
generic `execute()` escape hatch for anything the typed methods don't cover.

Built against the [Linear developer docs](https://linear.app/developers).

## Highlights

- **One endpoint, one client.** Talk to `https://api.linear.app/graphql` through a
  single [`LinearClient`][linear_python.LinearClient].
- **Request in, Response out.** Each call is typed end to end, e.g.
  [`IssueCreateRequest`][linear_python.IssueCreateRequest] →
  [`CreateIssueResponse`][linear_python.CreateIssueResponse].
- **Pydantic models.** Snake_case attributes with camelCase aliases; validation and
  serialisation come for free.
- **Both auth methods.** Personal API keys and OAuth 2.0 access tokens.
- **Pagination made trivial.** `paginate()` follows the cursor for you.
- **Real error handling.** Auth, rate-limit, and GraphQL errors map to typed
  exceptions.
- **No lock-in.** `execute()` runs any raw GraphQL query or mutation.

## Install

Distributed as assets on [GitHub Releases](https://github.com/ewinter-hackerone/linear-python/releases)
(not on PyPI):

```sh
uv pip install https://github.com/ewinter-hackerone/linear-python/releases/download/v0.1.0/linear_python-0.1.0-py3-none-any.whl
```

Requires Python 3.14+. See [Getting started](getting-started.md) for more install
options.

## A 30-second tour

```python
from linear_python import LinearClient, IssueCreateRequest, IssuesRequest

with LinearClient(api_key="lin_api_...") as client:
    print(client.viewer().viewer.name)

    created = client.create_issue(
        IssueCreateRequest(
            team_id="9cfb482a-81e3-4154-b5b9-2c805e70a02d",
            title="New exception",
            priority=2,
        )
    )
    print(created.issue.identifier)

    for issue in client.paginate(client.issues, IssuesRequest(filter={"priority": {"eq": 1}})):
        print(issue.identifier, issue.title)
```

Continue with [Getting started](getting-started.md), the
[Usage guide](usage.md), or jump to the [API reference](api/client.md).

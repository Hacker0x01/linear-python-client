# Usage guide

Every client method takes a single typed **request** model (see the
[Requests reference](api/requests.md)) and returns a dedicated **response** model (see
the [Responses reference](api/responses.md)). All examples assume an authenticated
client:

```python
from linear_python import LinearClient

client = LinearClient(api_key="lin_api_...")
```

## Requests and responses

The pattern is always the same — build a `*Request`, get a `*Response`:

```python
from linear_python import IssueRequest

response = client.issue(IssueRequest(id="ENG-123"))  # -> IssueResponse
issue = response.issue                                # -> Issue | None
```

Request fields are Pythonic snake_case with camelCase aliases, so both spellings
work and serialisation back to the API is automatic:

```python
from linear_python import IssueCreateRequest

IssueCreateRequest(team_id="t1", title="Hi")   # snake_case
IssueCreateRequest(teamId="t1", title="Hi")    # camelCase — same thing
```

## Fetching single entities

Each "get one" request takes an id (issues also accept their human identifier such as
`ENG-123`). The response wraps the entity, which is `None` if nothing matches.

```python
from linear_python import IssueRequest, TeamRequest, ProjectRequest, UserRequest

issue = client.issue(IssueRequest(id="ENG-123")).issue
print(issue.title, issue.state.name, issue.assignee.name)

team = client.team(TeamRequest(id="9cfb482a-81e3-4154-b5b9-2c805e70a02d")).team
project = client.project(ProjectRequest(id="...")).project
user = client.user(UserRequest(id="...")).user
```

## Listing, filtering & ordering

List methods take a `*Request` carrying `first`, `after`, and a `filter` dict (mapped
directly to Linear's [filtering syntax](https://linear.app/developers/filtering)), and
return a response that holds `.nodes` and `.page_info`. The request is optional — omit
it for the first page, unfiltered.

```python
from linear_python import IssuesRequest

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

Responses are iterable and sized, so you can also loop directly:

```python
for issue in client.issues(IssuesRequest(first=10)):
    print(issue.identifier)
```

### Filter examples

```python
# OR across conditions
client.issues(IssuesRequest(filter={"or": [{"priority": {"eq": 1}}, {"priority": {"eq": 2}}]}))

# Relationship filter
client.issues(IssuesRequest(filter={"team": {"key": {"eq": "ENG"}}}))

# Relative time (ISO-8601 duration): issues created in the last two weeks
client.issues(IssuesRequest(filter={"createdAt": {"gt": "-P2W"}}))
```

## Pagination

Use [`paginate()`][linear_python.client.LinearClient.paginate] to transparently walk
every page of any list method. Pass the method and a starting request; it follows the
cursor until there are no more results.

```python
from linear_python import IssuesRequest, TeamsRequest

for issue in client.paginate(client.issues, IssuesRequest(filter={"state": {"type": {"eq": "started"}}})):
    print(issue.identifier, issue.title)

# Works with any list method, with a custom page size:
for team in client.paginate(client.teams, TeamsRequest(), page_size=100):
    print(team.key, team.name)
```

## Creating and updating issues

Mutation responses expose `success` alongside the affected entity.

```python
from linear_python import IssueCreateRequest, IssueUpdateRequest, IssueArchiveRequest

created = client.create_issue(
    IssueCreateRequest(
        team_id="9cfb482a-81e3-4154-b5b9-2c805e70a02d",
        title="New exception",
        description="More detailed error report in **markdown**",
        priority=2,
        label_ids=["..."],
    )
)
print(created.success, created.issue.identifier)

client.update_issue(IssueUpdateRequest(id=created.issue.id, title="Renamed", priority=1))
client.archive_issue(IssueArchiveRequest(id=created.issue.id))
```

Any field accepted by Linear's `IssueCreateInput` / `IssueUpdateInput` can be passed
as an extra keyword argument using its camelCase API name (e.g. `dueDate="2026-01-01"`),
even if it isn't an explicit field on the request model.

## Comments

```python
from linear_python import CommentCreateRequest, CommentsRequest

client.create_comment(CommentCreateRequest(issue_id=created.issue.id, body="On it 👍"))

for comment in client.comments(CommentsRequest(issue_id=created.issue.id)):
    print(comment.user.name, comment.body)
```

## Workflow states & labels

```python
from linear_python import WorkflowStatesRequest, IssueLabelsRequest

states = client.workflow_states(WorkflowStatesRequest(team_id="..."))
labels = client.issue_labels(IssueLabelsRequest(first=100))
```

## Raw GraphQL

Anything not covered by a typed method can be run directly with
[`execute()`][linear_python.client.LinearClient.execute], which returns the `data`
object and raises on errors.

```python
data = client.execute(
    """
    query($id: String!) {
      issue(id: $id) {
        id
        title
        attachments { nodes { url title } }
      }
    }
    """,
    {"id": "ENG-123"},
)
print(data["issue"]["attachments"]["nodes"])
```

## Error handling

All exceptions subclass [`LinearError`][linear_python.LinearError]:

| Exception | Raised when |
|-----------|-------------|
| [`LinearAuthenticationError`][linear_python.LinearAuthenticationError] | Credentials are rejected (HTTP 401/403 or an auth error code) |
| [`LinearRateLimitError`][linear_python.LinearRateLimitError] | A rate limit is hit (`RATELIMITED`); carries the `X-RateLimit-*` header values |
| [`LinearGraphQLError`][linear_python.LinearGraphQLError] | The API returns GraphQL `errors`; exposes `.errors` and `.code` |
| [`LinearNetworkError`][linear_python.LinearNetworkError] | The request never produced a usable response |

```python
from linear_python import LinearClient, LinearRateLimitError, IssuesRequest

try:
    client.issues(IssuesRequest(first=100))
except LinearRateLimitError as exc:
    print("Rate limited; resets at", exc.requests_reset)
```

## Rate limits

Linear allows roughly **5,000 requests/hour** for API keys and OAuth apps, with a
separate complexity budget. The client surfaces the relevant `X-RateLimit-*` header
values on [`LinearRateLimitError`][linear_python.LinearRateLimitError] when a limit is
hit. See the [rate limiting docs](https://linear.app/developers/rate-limiting) for the
full details.

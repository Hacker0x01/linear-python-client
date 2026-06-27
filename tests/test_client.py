"""Unit tests for LinearClient using a mocked GraphQL endpoint (no network)."""

from __future__ import annotations

import httpx
import pytest
import respx

from linear_python_client import (
    CreateIssueResponse,
    IssueArchiveRequest,
    IssueCreateRequest,
    IssueRequest,
    IssuesRequest,
    IssuesResponse,
    IssueUpdateRequest,
    LinearAuthenticationError,
    LinearClient,
    LinearGraphQLError,
    LinearRateLimitError,
    LinearServerError,
    ViewerResponse,
)
from linear_python_client.client import DEFAULT_ENDPOINT


def gql_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


# -- auth header selection --------------------------------------------------


@respx.mock
def test_api_key_sent_verbatim() -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(return_value=gql_response({"viewer": {"id": "1"}}))
    with LinearClient(api_key="lin_api_abc") as client:
        client.viewer()
    assert route.calls.last.request.headers["Authorization"] == "lin_api_abc"


@respx.mock
def test_oauth_token_uses_bearer() -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(return_value=gql_response({"viewer": {"id": "1"}}))
    with LinearClient(access_token="oauth-token") as client:
        client.viewer()
    assert route.calls.last.request.headers["Authorization"] == "Bearer oauth-token"


def test_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    with pytest.raises(ValueError):
        LinearClient()


def test_rejects_both_credentials() -> None:
    with pytest.raises(ValueError):
        LinearClient(api_key="a", access_token="b")


def test_falls_back_to_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "env-key")
    client = LinearClient()
    assert client._headers["Authorization"] == "env-key"
    client.close()


# -- requests: field aliasing & serialization ------------------------------


def test_request_aliases_snake_to_camel() -> None:
    req = IssueCreateRequest(team_id="t1", title="Hi", assignee_id="u1", priority=2)
    variables = req.to_input()
    assert variables == {"teamId": "t1", "title": "Hi", "assigneeId": "u1", "priority": 2}


def test_request_accepts_camel_or_snake() -> None:
    # populate_by_name=True means both spellings construct the same model.
    by_snake = IssuesRequest(order_by="updatedAt", first=5)
    by_camel = IssuesRequest.model_validate({"orderBy": "updatedAt", "first": 5})
    expected = {"first": 5, "orderBy": "updatedAt"}
    assert by_snake.to_variables() == by_camel.to_variables() == expected


def test_request_passes_through_extra_fields() -> None:
    req = IssueCreateRequest(team_id="t1", title="x", dueDate="2026-01-01")
    assert req.to_input()["dueDate"] == "2026-01-01"


# -- queries ----------------------------------------------------------------


@respx.mock
def test_viewer(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {"viewer": {"id": "u1", "name": "Ada", "email": "ada@example.com"}}
        )
    )
    resp = client.viewer()
    assert isinstance(resp, ViewerResponse)
    assert resp.viewer is not None
    assert resp.viewer.id == "u1"
    assert resp.viewer.name == "Ada"


@respx.mock
def test_issue_parses_nested_and_aliases(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {
                "issue": {
                    "id": "i1",
                    "identifier": "ENG-1",
                    "title": "First",
                    "createdAt": "2024-01-01T12:00:00.000Z",
                    "assignee": {"id": "u1", "displayName": "ada"},
                    "team": {"id": "t1", "key": "ENG"},
                    "state": {"id": "s1", "name": "Todo", "type": "unstarted"},
                    "labels": {"nodes": [{"id": "l1", "name": "bug"}]},
                }
            }
        )
    )
    issue = client.issue(IssueRequest(id="ENG-1")).issue
    assert issue is not None
    assert issue.identifier == "ENG-1"
    assert issue.assignee.display_name == "ada"  # camelCase alias parsed
    assert issue.created_at.year == 2024  # parsed into datetime
    assert issue.team.key == "ENG"
    assert issue.labels[0].name == "bug"  # nested connection unwrapped


@respx.mock
def test_issues_parses_connection(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {
                "issues": {
                    "nodes": [
                        {"id": "i1", "identifier": "ENG-1", "title": "First"},
                        {"id": "i2", "identifier": "ENG-2", "title": "Second"},
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": "cursor2"},
                }
            }
        )
    )
    resp = client.issues(IssuesRequest(first=2))
    assert isinstance(resp, IssuesResponse)
    assert len(resp) == 2
    assert [issue.identifier for issue in resp] == ["ENG-1", "ENG-2"]
    assert resp.page_info.has_next_page is False
    assert resp.page_info.end_cursor == "cursor2"


@respx.mock
def test_issues_sends_filter_and_pagination_vars(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}})
    )
    client.issues(IssuesRequest(first=10, filter={"priority": {"eq": 1}}, order_by="updatedAt"))
    body = route.calls.last.request.content.decode()
    assert '"first":10' in body
    assert '"priority"' in body
    assert '"orderBy":"updatedAt"' in body


@respx.mock
def test_issues_defaults_to_empty_request(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issues": {"nodes": [], "pageInfo": {"hasNextPage": False}}})
    )
    resp = client.issues()  # no request -> first page, no filter
    assert resp.nodes == []


# -- mutations --------------------------------------------------------------


@respx.mock
def test_create_issue(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {"issueCreate": {"success": True, "issue": {"id": "i9", "title": "New exception"}}}
        )
    )
    _team = "43a11e2e-88af-4184-882b-45ec14d36ca9"
    resp = client.create_issue(IssueCreateRequest(team_id=_team, title="New exception", priority=2))
    assert isinstance(resp, CreateIssueResponse)
    assert resp.success is True
    assert resp.issue.id == "i9"
    body = route.calls.last.request.content.decode()
    assert f'"teamId":"{_team}"' in body
    assert '"priority":2' in body


@respx.mock
def test_archive_issue(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issueArchive": {"success": True}})
    )
    assert client.archive_issue(IssueArchiveRequest(id="i1")).success is True


def test_update_issue_requires_fields(client: LinearClient) -> None:
    with pytest.raises(ValueError):
        client.update_issue(IssueUpdateRequest(id="i1"))


# -- pagination -------------------------------------------------------------


@respx.mock
def test_paginate_follows_cursor(client: LinearClient) -> None:
    page_one = gql_response(
        {
            "issues": {
                "nodes": [{"id": "i1", "title": "A"}, {"id": "i2", "title": "B"}],
                "pageInfo": {"hasNextPage": True, "endCursor": "CUR1"},
            }
        }
    )
    page_two = gql_response(
        {
            "issues": {
                "nodes": [{"id": "i3", "title": "C"}],
                "pageInfo": {"hasNextPage": False, "endCursor": "CUR2"},
            }
        }
    )
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[page_one, page_two])

    titles = [
        issue.title for issue in client.paginate(client.issues, IssuesRequest(), page_size=2)
    ]
    assert titles == ["A", "B", "C"]
    assert route.call_count == 2
    # Second request should carry the cursor from page one and keep page_size.
    second_body = route.calls[1].request.content.decode()
    assert '"after":"CUR1"' in second_body
    assert '"first":2' in second_body


# -- error handling ---------------------------------------------------------


@respx.mock
def test_rate_limit_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            400,
            json={"errors": [{"message": "rate limited", "extensions": {"code": "RATELIMITED"}}]},
            headers={
                "X-RateLimit-Requests-Limit": "5000",
                "X-RateLimit-Requests-Remaining": "0",
                "X-RateLimit-Requests-Reset": "1700000000000",
                "X-Complexity": "150",
                "X-RateLimit-Endpoint-Requests-Limit": "50",
                "X-RateLimit-Endpoint-Requests-Remaining": "0",
                "X-RateLimit-Endpoint-Name": "issues",
            },
        )
    )
    with pytest.raises(LinearRateLimitError) as exc_info:
        client.issues()
    err = exc_info.value
    assert err.requests_limit == 5000
    assert err.requests_remaining == 0
    assert err.requests_reset == 1700000000000
    assert err.query_complexity == 150
    assert err.endpoint_requests_limit == 50
    assert err.endpoint_requests_remaining == 0
    assert err.endpoint_name == "issues"


@respx.mock
def test_server_error_raised_on_5xx(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(503, text="overloaded"))
    with pytest.raises(LinearServerError) as exc_info:
        client.viewer()
    assert exc_info.value.status_code == 503


@respx.mock
def test_authentication_error_status(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(401, json={}))
    with pytest.raises(LinearAuthenticationError):
        client.viewer()


@respx.mock
def test_generic_graphql_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "Field error", "extensions": {"code": "INTERNAL"}}]},
        )
    )
    with pytest.raises(LinearGraphQLError) as exc_info:
        client.issue(IssueRequest(id="i1"))
    assert exc_info.value.code == "INTERNAL"
    assert "Field error" in str(exc_info.value)

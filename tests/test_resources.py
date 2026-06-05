"""Coverage of every LinearClient resource method, with a mocked endpoint."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from linear_python_client import (
    CommentCreateRequest,
    CommentRequest,
    CommentsRequest,
    IssueLabelsRequest,
    IssueUpdateRequest,
    LinearClient,
    ProjectRequest,
    ProjectsRequest,
    TeamRequest,
    UserRequest,
    UsersRequest,
    WorkflowStatesRequest,
)
from linear_python_client.client import DEFAULT_ENDPOINT


def gql_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def last_variables(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content.decode()).get("variables", {})


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


# -- single-entity getters --------------------------------------------------


@respx.mock
def test_user(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"user": {"id": "u1", "name": "A"}})
    )
    assert client.user(UserRequest(id="u1")).user.name == "A"


@respx.mock
def test_team(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"team": {"id": "t1", "key": "ENG"}})
    )
    assert client.team(TeamRequest(id="t1")).team.key == "ENG"


@respx.mock
def test_project(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"project": {"id": "p1", "name": "Roadmap"}})
    )
    assert client.project(ProjectRequest(id="p1")).project.name == "Roadmap"


@respx.mock
def test_comment(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"comment": {"id": "c1", "body": "hi"}})
    )
    assert client.comment(CommentRequest(id="c1")).comment.body == "hi"


@respx.mock
def test_getter_returns_none_when_absent(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=gql_response({"user": None}))
    assert client.user(UserRequest(id="missing")).user is None


# -- list methods -----------------------------------------------------------


@respx.mock
def test_users(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"users": {"nodes": [{"id": "u1"}], "pageInfo": {}}})
    )
    resp = client.users(UsersRequest(first=1))
    assert [u.id for u in resp] == ["u1"]


@respx.mock
def test_teams_defaults_without_request(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"teams": {"nodes": [], "pageInfo": {}}})
    )
    assert client.teams().nodes == []
    assert last_variables(route) == {}  # empty request -> no variables


@respx.mock
def test_projects(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"projects": {"nodes": [{"id": "p1"}], "pageInfo": {}}})
    )
    assert len(client.projects(ProjectsRequest())) == 1


@respx.mock
def test_issue_labels(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issueLabels": {"nodes": [{"id": "l1", "name": "bug"}]}})
    )
    assert client.issue_labels(IssueLabelsRequest(first=50)).nodes[0].name == "bug"


# -- convenience scoping (issue_id / team_id merged into filter) ------------


@respx.mock
def test_comments_scoped_to_issue(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"comments": {"nodes": [], "pageInfo": {}}})
    )
    client.comments(CommentsRequest(issue_id="i1"))
    variables = last_variables(route)
    assert variables["filter"] == {"issue": {"id": {"eq": "i1"}}}
    assert "issueId" not in variables  # convenience field is not sent raw


@respx.mock
def test_comments_unscoped(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"comments": {"nodes": [], "pageInfo": {}}})
    )
    client.comments()  # no issue_id -> no filter added
    assert "filter" not in last_variables(route)


@respx.mock
def test_comments_merges_issue_id_with_existing_filter(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"comments": {"nodes": [], "pageInfo": {}}})
    )
    client.comments(CommentsRequest(issue_id="i1", filter={"body": {"contains": "x"}}))
    variables = last_variables(route)
    assert variables["filter"] == {"issue": {"id": {"eq": "i1"}}, "body": {"contains": "x"}}


@respx.mock
def test_workflow_states_scoped_to_team(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"workflowStates": {"nodes": [{"id": "s1"}], "pageInfo": {}}})
    )
    resp = client.workflow_states(WorkflowStatesRequest(team_id="t1"))
    assert resp.nodes[0].id == "s1"
    assert last_variables(route)["filter"] == {"team": {"id": {"eq": "t1"}}}


@respx.mock
def test_workflow_states_unscoped(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"workflowStates": {"nodes": [], "pageInfo": {}}})
    )
    client.workflow_states()
    assert "filter" not in last_variables(route)


# -- mutations --------------------------------------------------------------


@respx.mock
def test_update_issue_success(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {"issueUpdate": {"success": True, "issue": {"id": "i1", "title": "Renamed"}}}
        )
    )
    resp = client.update_issue(IssueUpdateRequest(id="i1", title="Renamed", priority=1))
    assert resp.success is True
    assert resp.issue.title == "Renamed"
    variables = last_variables(route)
    assert variables["id"] == "i1"
    assert variables["input"] == {"title": "Renamed", "priority": 1}  # id excluded from input


@respx.mock
def test_create_comment(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {"commentCreate": {"success": True, "comment": {"id": "c9", "body": "On it"}}}
        )
    )
    resp = client.create_comment(CommentCreateRequest(issue_id="i1", body="On it"))
    assert resp.success is True
    assert resp.comment.id == "c9"
    assert last_variables(route)["input"] == {"issueId": "i1", "body": "On it"}


# -- lifecycle --------------------------------------------------------------


def test_injected_http_client_is_not_closed() -> None:
    http = httpx.Client()
    client = LinearClient(api_key="k", http_client=http)
    client.close()
    assert not http.is_closed  # caller retains ownership
    http.close()


def test_owned_http_client_is_closed() -> None:
    client = LinearClient(api_key="k")
    client.close()
    assert client._http.is_closed

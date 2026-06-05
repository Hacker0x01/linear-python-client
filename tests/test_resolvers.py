"""Coverage of the name/key -> entity resolver methods."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from linear_python_client import (
    FindLabelRequest,
    FindProjectRequest,
    FindTeamRequest,
    FindUserRequest,
    IssueLabelResponse,
    LinearClient,
    ProjectResponse,
    TeamResponse,
    UserResponse,
)
from linear_python_client.client import DEFAULT_ENDPOINT


def gql_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def last_variables(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content.decode()).get("variables", {})


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


# -- team -------------------------------------------------------------------


@respx.mock
def test_find_team_by_key(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"teams": {"nodes": [{"id": "t1", "key": "RAV"}]}})
    )
    resp = client.find_team(FindTeamRequest(key="RAV"))
    assert isinstance(resp, TeamResponse)
    assert resp.team.id == "t1"
    variables = last_variables(route)
    assert variables["filter"] == {"key": {"eq": "RAV"}}
    assert variables["first"] == 1


@respx.mock
def test_find_team_by_name(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"teams": {"nodes": [{"id": "t1", "name": "Ravens"}]}})
    )
    client.find_team(FindTeamRequest(name="Ravens"))
    assert last_variables(route)["filter"] == {"name": {"eqIgnoreCase": "Ravens"}}


@respx.mock
def test_find_team_no_match(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=gql_response({"teams": {"nodes": []}}))
    assert client.find_team(FindTeamRequest(key="NOPE")).team is None


def test_find_team_requires_a_field() -> None:
    with pytest.raises(ValueError):
        FindTeamRequest()


# -- user -------------------------------------------------------------------


@respx.mock
def test_find_user_by_name_matches_name_or_display_name(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"users": {"nodes": [{"id": "u1", "name": "Elijah Winter"}]}})
    )
    resp = client.find_user(FindUserRequest(name="Elijah Winter"))
    assert isinstance(resp, UserResponse)
    assert resp.user.id == "u1"
    assert last_variables(route)["filter"] == {
        "or": [
            {"name": {"eqIgnoreCase": "Elijah Winter"}},
            {"displayName": {"eqIgnoreCase": "Elijah Winter"}},
        ]
    }


@respx.mock
def test_find_user_by_email(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"users": {"nodes": [{"id": "u1"}]}})
    )
    client.find_user(FindUserRequest(email="me@example.com"))
    assert last_variables(route)["filter"] == {"email": {"eqIgnoreCase": "me@example.com"}}


@respx.mock
def test_find_user_by_name_and_email_combines_with_and(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"users": {"nodes": []}})
    )
    client.find_user(FindUserRequest(name="Ada", email="ada@example.com"))
    filter_ = last_variables(route)["filter"]
    assert "and" in filter_ and len(filter_["and"]) == 2


def test_find_user_requires_a_field() -> None:
    with pytest.raises(ValueError):
        FindUserRequest()


# -- project ----------------------------------------------------------------


@respx.mock
def test_find_project(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"projects": {"nodes": [{"id": "p1", "name": "Roadmap"}]}})
    )
    resp = client.find_project(FindProjectRequest(name="roadmap"))
    assert isinstance(resp, ProjectResponse)
    assert resp.project.name == "Roadmap"
    assert last_variables(route)["filter"] == {"name": {"eqIgnoreCase": "roadmap"}}


# -- label ------------------------------------------------------------------


@respx.mock
def test_find_label_scoped_to_team(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issueLabels": {"nodes": [{"id": "l1", "name": "bug"}]}})
    )
    resp = client.find_label(FindLabelRequest(name="Bug", team_id="t1"))
    assert isinstance(resp, IssueLabelResponse)
    assert resp.label.id == "l1"
    assert last_variables(route)["filter"] == {
        "name": {"eqIgnoreCase": "Bug"},
        "team": {"id": {"eq": "t1"}},
    }


@respx.mock
def test_find_label_no_team(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issueLabels": {"nodes": []}})
    )
    assert client.find_label(FindLabelRequest(name="bug")).label is None
    assert last_variables(route)["filter"] == {"name": {"eqIgnoreCase": "bug"}}

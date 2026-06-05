"""Coverage of labels, status updates, and full issue details."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from linear_python_client import (
    AddLabelResponse,
    FindWorkflowStateRequest,
    IssueAddLabelRequest,
    IssueDetail,
    IssueDetailsResponse,
    IssueRemoveLabelRequest,
    IssueRequest,
    IssueSetStateRequest,
    LinearClient,
    RemoveLabelResponse,
    UpdateIssueResponse,
    WorkflowStateResponse,
)
from linear_python_client.client import DEFAULT_ENDPOINT


def gql_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def last_body(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content.decode())


def last_variables(route: respx.Route) -> dict:
    return last_body(route).get("variables", {})


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


# -- labels -----------------------------------------------------------------


@respx.mock
def test_add_label(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {
                "issueAddLabel": {
                    "success": True,
                    "issue": {"id": "i1", "labels": {"nodes": [{"id": "l1", "name": "bug"}]}},
                }
            }
        )
    )
    resp = client.add_label(IssueAddLabelRequest(id="i1", label_id="l1"))
    assert isinstance(resp, AddLabelResponse)
    assert resp.success is True
    assert resp.issue.labels[0].name == "bug"
    body = last_body(route)
    assert "issueAddLabel" in body["query"]
    assert body["variables"] == {"id": "i1", "labelId": "l1"}


@respx.mock
def test_remove_label(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"issueRemoveLabel": {"success": True, "issue": {"id": "i1"}}})
    )
    resp = client.remove_label(IssueRemoveLabelRequest(id="i1", label_id="l1"))
    assert isinstance(resp, RemoveLabelResponse)
    assert resp.success is True
    assert resp.issue.id == "i1"
    assert "issueRemoveLabel" in last_body(route)["query"]
    assert last_variables(route) == {"id": "i1", "labelId": "l1"}


# -- status (workflow state) ------------------------------------------------


@respx.mock
def test_set_issue_state(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {"issueUpdate": {"success": True, "issue": {"id": "i1", "state": {"name": "Done"}}}}
        )
    )
    resp = client.set_issue_state(IssueSetStateRequest(id="i1", state_id="s-done"))
    assert isinstance(resp, UpdateIssueResponse)
    assert resp.success is True
    assert resp.issue.state.name == "Done"
    variables = last_variables(route)
    assert variables == {"id": "i1", "input": {"stateId": "s-done"}}


@respx.mock
def test_find_workflow_state_match(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {"workflowStates": {"nodes": [{"id": "s1", "name": "In Progress", "type": "started"}]}}
        )
    )
    resp = client.find_workflow_state(FindWorkflowStateRequest(team_id="t1", name="in progress"))
    assert isinstance(resp, WorkflowStateResponse)
    assert resp.state.id == "s1"
    assert resp.state.name == "In Progress"
    variables = last_variables(route)
    assert variables["filter"] == {
        "team": {"id": {"eq": "t1"}},
        "name": {"eqIgnoreCase": "in progress"},
    }
    assert variables["first"] == 1


@respx.mock
def test_find_workflow_state_no_match(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response({"workflowStates": {"nodes": []}})
    )
    resp = client.find_workflow_state(FindWorkflowStateRequest(team_id="t1", name="Nope"))
    assert resp.state is None


# -- full details -----------------------------------------------------------


@respx.mock
def test_issue_details_parses_all_relations(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(
        return_value=gql_response(
            {
                "issue": {
                    "id": "i1",
                    "identifier": "ENG-1",
                    "title": "Parent task",
                    "labels": {"nodes": [{"id": "l1", "name": "bug"}]},
                    "comments": {"nodes": [{"id": "c1", "body": "hi", "user": {"name": "Ada"}}]},
                    "attachments": {
                        "nodes": [{"id": "a1", "title": "PR", "url": "https://example.com"}]
                    },
                    "project": {"id": "p1", "name": "Roadmap"},
                    "cycle": {"id": "cy1", "number": 7, "name": "Cycle 7"},
                    "parent": {"id": "i0", "identifier": "ENG-0", "title": "Epic"},
                    "children": {"nodes": [{"id": "i2", "identifier": "ENG-2", "title": "Sub"}]},
                    "subscribers": {"nodes": [{"id": "u1", "name": "Ada"}]},
                    "relations": {
                        "nodes": [
                            {"type": "blocks", "relatedIssue": {"id": "i9", "identifier": "ENG-9"}}
                        ]
                    },
                }
            }
        )
    )
    resp = client.issue_details(IssueRequest(id="ENG-1"))
    assert isinstance(resp, IssueDetailsResponse)
    issue = resp.issue
    assert isinstance(issue, IssueDetail)
    assert issue.identifier == "ENG-1"
    assert issue.labels[0].name == "bug"
    assert issue.comments[0].body == "hi"
    assert issue.comments[0].user.name == "Ada"
    assert issue.attachments[0].url == "https://example.com"
    assert issue.project.name == "Roadmap"
    assert issue.cycle.number == 7
    assert issue.parent.identifier == "ENG-0"
    assert issue.children[0].identifier == "ENG-2"
    assert issue.subscribers[0].name == "Ada"
    assert issue.relations[0].type == "blocks"
    assert issue.relations[0].related_issue.identifier == "ENG-9"
    assert "IssueDetailFields" in last_body(route)["query"]


@respx.mock
def test_issue_details_missing_returns_none(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=gql_response({"issue": None}))
    assert client.issue_details(IssueRequest(id="missing")).issue is None


def test_issue_detail_collections_default_empty() -> None:
    issue = IssueDetail.model_validate({"id": "i1", "title": "x"})
    assert issue.comments == []
    assert issue.attachments == []
    assert issue.children == []
    assert issue.subscribers == []
    assert issue.relations == []
    assert issue.parent is None
    assert issue.project is None
    assert issue.cycle is None

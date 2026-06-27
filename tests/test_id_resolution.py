"""Coverage of the automatic non-UUID → UUID resolution in create_issue / update_issue."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from linear_python_client import (
    IssueCreateRequest,
    IssueUpdateRequest,
    LinearClient,
)
from linear_python_client.client import DEFAULT_ENDPOINT, _is_uuid

# ---------------------------------------------------------------------------
# Sample UUIDs
# ---------------------------------------------------------------------------

_TEAM_UUID = "43a11e2e-88af-4184-882b-45ec14d36ca9"
_USER_UUID = "11111111-aaaa-bbbb-cccc-000000000001"
_PROJECT_UUID = "22222222-aaaa-bbbb-cccc-000000000002"
_LABEL_UUID = "33333333-aaaa-bbbb-cccc-000000000003"
_LABEL2_UUID = "44444444-aaaa-bbbb-cccc-000000000004"
_STATE_UUID = "55555555-aaaa-bbbb-cccc-000000000005"
_ISSUE_UUID = "66666666-aaaa-bbbb-cccc-000000000006"


# ---------------------------------------------------------------------------
# Response factories
# ---------------------------------------------------------------------------


def gql(data: dict) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def team_hit(id: str = _TEAM_UUID) -> httpx.Response:
    return gql({"teams": {"nodes": [{"id": id, "key": "ENG", "name": "Engineering"}]}})


def team_miss() -> httpx.Response:
    return gql({"teams": {"nodes": []}})


def user_hit(id: str = _USER_UUID) -> httpx.Response:
    return gql({"users": {"nodes": [{"id": id, "name": "Alice", "email": "alice@example.com"}]}})


def user_miss() -> httpx.Response:
    return gql({"users": {"nodes": []}})


def project_hit(id: str = _PROJECT_UUID) -> httpx.Response:
    return gql({"projects": {"nodes": [{"id": id, "name": "Roadmap"}]}})


def project_miss() -> httpx.Response:
    return gql({"projects": {"nodes": []}})


def label_hit(id: str = _LABEL_UUID) -> httpx.Response:
    return gql({"issueLabels": {"nodes": [{"id": id, "name": "bug"}]}})


def label_miss() -> httpx.Response:
    return gql({"issueLabels": {"nodes": []}})


def state_hit(id: str = _STATE_UUID) -> httpx.Response:
    return gql({"workflowStates": {"nodes": [{"id": id, "name": "In Progress", "type": "started"}]}})


def state_miss() -> httpx.Response:
    return gql({"workflowStates": {"nodes": []}})


def create_ok(id: str = _ISSUE_UUID) -> httpx.Response:
    return gql({"issueCreate": {"success": True, "issue": {"id": id, "title": "x"}}})


def update_ok() -> httpx.Response:
    return gql({"issueUpdate": {"success": True, "issue": {"id": "i1"}}})


def last_variables(route: respx.Route) -> dict:
    return json.loads(route.calls.last.request.content.decode()).get("variables", {})


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


# ---------------------------------------------------------------------------
# _is_uuid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("43a11e2e-88af-4184-882b-45ec14d36ca9", True),
        ("00000000-0000-0000-0000-000000000000", True),
        ("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE", True),
        ("Engineering", False),
        ("alerts-a5f005322339", False),
        ("alert-type/sentinel-one", False),
        ("alice@example.com", False),
        ("", False),
        ("43a11e2e-88af-4184-882b-45ec14d36ca9 ", False),  # trailing space
    ],
)
def test_is_uuid(value: str, expected: bool) -> None:
    assert _is_uuid(value) is expected


# ---------------------------------------------------------------------------
# team_id resolution
# ---------------------------------------------------------------------------


@respx.mock
def test_team_name_resolved_to_uuid(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), create_ok()])
    client.create_issue(IssueCreateRequest(team_id="Engineering", title="x"))
    assert route.call_count == 2  # 1 find_team + 1 create


@respx.mock
def test_team_uuid_skips_lookup(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[create_ok()])
    client.create_issue(IssueCreateRequest(team_id=_TEAM_UUID, title="x"))
    assert route.call_count == 1  # create only, no find_team


@respx.mock
def test_team_resolved_by_key_when_name_not_found(client: LinearClient) -> None:
    # First call (by name) misses; second call (by key) hits.
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_miss(), team_hit(), create_ok()])
    client.create_issue(IssueCreateRequest(team_id="ENG", title="x"))
    assert route.call_count == 3


@respx.mock
def test_resolved_team_uuid_sent_in_mutation(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(_TEAM_UUID), create_ok()])
    client.create_issue(IssueCreateRequest(team_id="Engineering", title="x"))
    mutation_vars = last_variables(route)
    assert mutation_vars["input"]["teamId"] == _TEAM_UUID


@respx.mock
def test_team_not_found_raises_value_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_miss(), team_miss()])
    with pytest.raises(ValueError, match="Team not found"):
        client.create_issue(IssueCreateRequest(team_id="Nope", title="x"))


# ---------------------------------------------------------------------------
# assignee_id resolution
# ---------------------------------------------------------------------------


@respx.mock
def test_assignee_name_resolved_to_uuid(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), user_hit(), create_ok()])
    client.create_issue(IssueCreateRequest(team_id="Engineering", title="x", assignee_id="Alice"))
    assert route.call_count == 3


@respx.mock
def test_assignee_email_resolved_to_uuid(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), user_hit(), create_ok()])
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", assignee_id="alice@example.com")
    )
    assert route.call_count == 3


@respx.mock
def test_assignee_uuid_skips_lookup(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), create_ok()])
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", assignee_id=_USER_UUID)
    )
    assert route.call_count == 2  # team + create, no user lookup


@respx.mock
def test_assignee_not_found_raises_value_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), user_miss()])
    with pytest.raises(ValueError, match="User not found"):
        client.create_issue(
            IssueCreateRequest(team_id="Engineering", title="x", assignee_id="Nobody")
        )


# ---------------------------------------------------------------------------
# project_id resolution
# ---------------------------------------------------------------------------


@respx.mock
def test_project_name_resolved_to_uuid(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), project_hit(), create_ok()])
    client.create_issue(IssueCreateRequest(team_id="Engineering", title="x", project_id="Roadmap"))
    assert route.call_count == 3


@respx.mock
def test_project_uuid_skips_lookup(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), create_ok()])
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", project_id=_PROJECT_UUID)
    )
    assert route.call_count == 2


@respx.mock
def test_project_not_found_raises_value_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), project_miss()])
    with pytest.raises(ValueError, match="Project not found"):
        client.create_issue(
            IssueCreateRequest(team_id="Engineering", title="x", project_id="Nope")
        )


# ---------------------------------------------------------------------------
# label_ids resolution
# ---------------------------------------------------------------------------


@respx.mock
def test_label_name_resolved_to_uuid(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), label_hit(), create_ok()])
    client.create_issue(IssueCreateRequest(team_id="Engineering", title="x", label_ids=["bug"]))
    assert route.call_count == 3


@respx.mock
def test_mixed_labels_only_resolves_non_uuids(client: LinearClient) -> None:
    # One UUID (pass-through) + one name (resolved) → only 1 label lookup.
    route = respx.post(DEFAULT_ENDPOINT).mock(
        side_effect=[team_hit(), label_hit(_LABEL2_UUID), create_ok()]
    )
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", label_ids=[_LABEL_UUID, "feature"])
    )
    assert route.call_count == 3  # team + 1 label + create (not 4)


@respx.mock
def test_all_uuid_labels_skip_lookup(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), create_ok()])
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", label_ids=[_LABEL_UUID])
    )
    assert route.call_count == 2


@respx.mock
def test_label_not_found_raises_value_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), label_miss()])
    with pytest.raises(ValueError, match="Label not found"):
        client.create_issue(
            IssueCreateRequest(team_id="Engineering", title="x", label_ids=["nope"])
        )


# ---------------------------------------------------------------------------
# state_id resolution
# ---------------------------------------------------------------------------


@respx.mock
def test_state_name_resolved_to_uuid(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), state_hit(), create_ok()])
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", state_id="In Progress")
    )
    assert route.call_count == 3


@respx.mock
def test_state_uuid_skips_lookup(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), create_ok()])
    client.create_issue(
        IssueCreateRequest(team_id="Engineering", title="x", state_id=_STATE_UUID)
    )
    assert route.call_count == 2


@respx.mock
def test_state_not_found_raises_value_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=[team_hit(), state_miss()])
    with pytest.raises(ValueError, match="Workflow state"):
        client.create_issue(
            IssueCreateRequest(team_id="Engineering", title="x", state_id="Nope")
        )


# ---------------------------------------------------------------------------
# update_issue resolution
# ---------------------------------------------------------------------------


@respx.mock
def test_update_resolves_assignee_by_name(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[user_hit(), update_ok()])
    client.update_issue(IssueUpdateRequest(id="i1", assignee_id="Alice"))
    assert route.call_count == 2


@respx.mock
def test_update_resolves_assignee_by_email(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[user_hit(), update_ok()])
    client.update_issue(IssueUpdateRequest(id="i1", assignee_id="alice@example.com"))
    assert route.call_count == 2


@respx.mock
def test_update_resolves_project_by_name(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[project_hit(), update_ok()])
    client.update_issue(IssueUpdateRequest(id="i1", project_id="Roadmap"))
    assert route.call_count == 2


@respx.mock
def test_update_resolves_labels_by_name(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[label_hit(), update_ok()])
    client.update_issue(IssueUpdateRequest(id="i1", label_ids=["bug"]))
    assert route.call_count == 2


@respx.mock
def test_update_uuid_fields_skip_lookup(client: LinearClient) -> None:
    route = respx.post(DEFAULT_ENDPOINT).mock(side_effect=[update_ok()])
    client.update_issue(
        IssueUpdateRequest(
            id="i1",
            assignee_id=_USER_UUID,
            project_id=_PROJECT_UUID,
            label_ids=[_LABEL_UUID],
        )
    )
    assert route.call_count == 1  # update only


def test_update_non_uuid_state_raises_value_error(client: LinearClient) -> None:
    with pytest.raises(ValueError, match="state_id cannot be resolved"):
        client.update_issue(IssueUpdateRequest(id="i1", state_id="In Progress"))

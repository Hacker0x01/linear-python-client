"""Coverage of model parsing and request serialization edge cases."""

from __future__ import annotations

from linear_python import (
    CommentCreateRequest,
    Issue,
    IssuesResponse,
    IssueUpdateRequest,
    PageInfo,
)


def test_issue_labels_accept_plain_list() -> None:
    # The validator unwraps {"nodes": [...]}, but a plain list must pass through too.
    issue = Issue.model_validate({"id": "i1", "labels": [{"id": "l1", "name": "bug"}]})
    assert issue.labels[0].name == "bug"


def test_issue_labels_default_empty() -> None:
    issue = Issue.model_validate({"id": "i1"})
    assert issue.labels == []


def test_connection_response_defaults() -> None:
    resp = IssuesResponse()
    assert list(resp) == []
    assert len(resp) == 0
    assert isinstance(resp.page_info, PageInfo)
    assert resp.page_info.has_next_page is False


def test_comment_create_request_to_input_with_extra() -> None:
    req = CommentCreateRequest(issue_id="i1", body="hi", createAsUser="Bot")
    assert req.to_input() == {"issueId": "i1", "body": "hi", "createAsUser": "Bot"}


def test_issue_update_request_to_input_excludes_id_and_unset() -> None:
    req = IssueUpdateRequest(id="i1", title="New")
    data = req.to_input()
    assert data == {"title": "New"}  # id removed, None fields omitted


def test_issue_update_request_empty_input() -> None:
    # Only id set -> nothing to update; to_input is empty (client raises on this).
    assert IssueUpdateRequest(id="i1").to_input() == {}

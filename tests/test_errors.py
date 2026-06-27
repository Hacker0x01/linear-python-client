"""Coverage of execute()'s error mapping and the exception types."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from linear_python_client import (
    IssuesRequest,
    LinearAuthenticationError,
    LinearClient,
    LinearGraphQLError,
    LinearNetworkError,
    LinearRateLimitError,
    LinearServerError,
)
from linear_python_client.client import DEFAULT_ENDPOINT, _build_error_message


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


# ---------------------------------------------------------------------------
# Network / transport errors
# ---------------------------------------------------------------------------


@respx.mock
def test_transport_error_becomes_network_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(LinearNetworkError, match="Request to Linear failed"):
        client.execute("query { viewer { id } }")


@respx.mock
def test_non_json_response_becomes_network_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(200, text="<html>nope</html>")
    )
    with pytest.raises(LinearNetworkError, match="non-JSON"):
        client.execute("query { viewer { id } }")


@respx.mock
def test_non_json_response_includes_body_preview(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(200, text="<html>bad gateway</html>")
    )
    with pytest.raises(LinearNetworkError) as exc_info:
        client.execute("query { viewer { id } }")
    assert "bad gateway" in str(exc_info.value)


@respx.mock
def test_4xx_without_graphql_errors_becomes_network_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(404, json={}))
    with pytest.raises(LinearNetworkError, match="HTTP 404"):
        client.execute("query { viewer { id } }")


# ---------------------------------------------------------------------------
# Server errors (5xx)
# ---------------------------------------------------------------------------


@respx.mock
def test_5xx_raises_linear_server_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(500, json={}))
    with pytest.raises(LinearServerError) as exc_info:
        client.execute("query { viewer { id } }")
    assert exc_info.value.status_code == 500


@respx.mock
def test_503_non_json_raises_server_error_with_body_preview(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(503, text="Service Unavailable")
    )
    with pytest.raises(LinearServerError) as exc_info:
        client.execute("query { viewer { id } }")
    assert exc_info.value.status_code == 503
    assert "Service Unavailable" in exc_info.value.body_preview


@respx.mock
def test_server_error_message_includes_status_code(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(502, text="Bad Gateway"))
    with pytest.raises(LinearServerError, match="HTTP 502"):
        client.execute("query { viewer { id } }")


def test_server_error_attributes() -> None:
    err = LinearServerError("oops", status_code=503, body_preview="bad gateway")
    assert err.status_code == 503
    assert err.body_preview == "bad gateway"
    assert str(err) == "oops"


def test_server_error_default_body_preview() -> None:
    err = LinearServerError("oops", status_code=500)
    assert err.body_preview == ""


# ---------------------------------------------------------------------------
# Authentication errors
# ---------------------------------------------------------------------------


@respx.mock
def test_authentication_error_code(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "nope", "extensions": {"code": "AUTHENTICATION_ERROR"}}]},
        )
    )
    with pytest.raises(LinearAuthenticationError, match="nope"):
        client.execute("query { viewer { id } }")


@respx.mock
def test_unauthenticated_code_raises_auth_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "not authed", "extensions": {"code": "UNAUTHENTICATED"}}]},
        )
    )
    with pytest.raises(LinearAuthenticationError, match="not authed"):
        client.execute("query { viewer { id } }")


@respx.mock
def test_forbidden_code_raises_auth_error(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "forbidden", "extensions": {"code": "FORBIDDEN"}}]},
        )
    )
    with pytest.raises(LinearAuthenticationError, match="forbidden"):
        client.execute("query { viewer { id } }")


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


@respx.mock
def test_rate_limit_tolerates_non_numeric_headers(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            400,
            json={"errors": [{"message": "slow down", "extensions": {"code": "RATELIMITED"}}]},
            headers={"X-RateLimit-Requests-Limit": "not-a-number"},
        )
    )
    with pytest.raises(LinearRateLimitError) as exc_info:
        client.issues(IssuesRequest())
    assert exc_info.value.requests_limit is None


@respx.mock
def test_rate_limit_captures_endpoint_and_complexity_headers(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            400,
            json={"errors": [{"message": "slow down", "extensions": {"code": "RATELIMITED"}}]},
            headers={
                "X-RateLimit-Requests-Limit": "2500",
                "X-RateLimit-Requests-Remaining": "0",
                "X-RateLimit-Requests-Reset": "1700000000000",
                "X-Complexity": "42",
                "X-RateLimit-Endpoint-Requests-Limit": "100",
                "X-RateLimit-Endpoint-Requests-Remaining": "0",
                "X-RateLimit-Endpoint-Requests-Reset": "1700000001000",
                "X-RateLimit-Endpoint-Name": "issueCreate",
            },
        )
    )
    with pytest.raises(LinearRateLimitError) as exc_info:
        client.issues(IssuesRequest())
    err = exc_info.value
    assert err.requests_limit == 2500
    assert err.requests_remaining == 0
    assert err.query_complexity == 42
    assert err.endpoint_requests_limit == 100
    assert err.endpoint_requests_remaining == 0
    assert err.endpoint_requests_reset == 1700000001000
    assert err.endpoint_name == "issueCreate"


def test_rate_limit_error_endpoint_fields_default_none() -> None:
    err = LinearRateLimitError("rate limited", requests_limit=2500)
    assert err.endpoint_requests_limit is None
    assert err.endpoint_name is None
    assert err.query_complexity is None
    assert err.requests_limit == 2500


# ---------------------------------------------------------------------------
# Partial success (200 + data + errors)
# ---------------------------------------------------------------------------


@respx.mock
def test_partial_success_raises_and_logs_warning(
    client: LinearClient, caplog: pytest.LogCaptureFixture
) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {"viewer": {"id": "u1"}},
                "errors": [{"message": "some fields failed"}],
            },
        )
    )
    with caplog.at_level(logging.WARNING, logger="linear_python_client.client"):
        with pytest.raises(LinearGraphQLError):
            client.execute("query { viewer { id } }")
    assert any("partial success" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Generic GraphQL errors
# ---------------------------------------------------------------------------


@respx.mock
def test_error_without_extensions_code(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "boom", "code": "INTERNAL"}]})
    )
    with pytest.raises(LinearGraphQLError) as exc_info:
        client.execute("query { viewer { id } }")
    assert exc_info.value.code == "INTERNAL"


@respx.mock
def test_graphql_error_with_no_code_at_all(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "plain failure"}]})
    )
    with pytest.raises(LinearGraphQLError) as exc_info:
        client.execute("query { viewer { id } }")
    assert exc_info.value.code is None
    assert "plain failure" in str(exc_info.value)


def test_graphql_error_code_is_none_without_a_code() -> None:
    err = LinearGraphQLError("boom", errors=[{"message": "no code here"}])
    assert err.code is None
    assert err.errors == [{"message": "no code here"}]


def test_graphql_error_defaults_to_empty_errors() -> None:
    err = LinearGraphQLError("boom")
    assert err.errors == []
    assert err.code is None


# ---------------------------------------------------------------------------
# _build_error_message
# ---------------------------------------------------------------------------


def test_build_error_message_basic() -> None:
    assert _build_error_message([{"message": "Something went wrong"}]) == "Something went wrong"


def test_build_error_message_empty_list() -> None:
    assert _build_error_message([]) == "GraphQL error"


def test_build_error_message_includes_code() -> None:
    errors = [{"message": "Bad input", "extensions": {"code": "BAD_USER_INPUT"}}]
    result = _build_error_message(errors)
    assert "[BAD_USER_INPUT]" in result
    assert "Bad input" in result


def test_build_error_message_prefers_user_presentable_message() -> None:
    errors = [
        {
            "message": "Argument Validation Error",
            "extensions": {
                "code": "BAD_USER_INPUT",
                "userPresentableMessage": "The project ID must be a valid UUID.",
            },
        }
    ]
    result = _build_error_message(errors)
    assert "The project ID must be a valid UUID." in result
    assert "Argument Validation Error" not in result


def test_build_error_message_falls_back_when_user_message_identical() -> None:
    errors = [
        {
            "message": "Same message",
            "extensions": {"userPresentableMessage": "Same message"},
        }
    ]
    assert _build_error_message(errors) == "Same message"


def test_build_error_message_includes_field_validation_errors() -> None:
    errors = [
        {
            "message": "Argument Validation Error",
            "extensions": {
                "code": "BAD_USER_INPUT",
                "errors": {
                    "projectId": ["projectId must be a UUID"],
                    "labelIds": ["each value must be a UUID"],
                },
            },
        }
    ]
    result = _build_error_message(errors)
    assert "projectId" in result
    assert "labelIds" in result
    assert "invalid fields" in result


def test_build_error_message_field_errors_as_string() -> None:
    errors = [
        {
            "message": "Validation failed",
            "extensions": {"errors": {"title": "title is required"}},
        }
    ]
    result = _build_error_message(errors)
    assert "title" in result
    assert "title is required" in result


def test_build_error_message_joins_multiple_errors() -> None:
    errors = [{"message": "Error one"}, {"message": "Error two"}]
    result = _build_error_message(errors)
    assert "Error one" in result
    assert "Error two" in result
    assert " | " in result

"""Coverage of execute()'s error mapping and the exception types."""

from __future__ import annotations

import httpx
import pytest
import respx

from linear_python import (
    IssuesRequest,
    LinearAuthenticationError,
    LinearClient,
    LinearGraphQLError,
    LinearNetworkError,
    LinearRateLimitError,
)
from linear_python.client import DEFAULT_ENDPOINT


@pytest.fixture
def client() -> LinearClient:
    return LinearClient(api_key="test-key")


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
def test_http_error_without_graphql_errors(client: LinearClient) -> None:
    respx.post(DEFAULT_ENDPOINT).mock(return_value=httpx.Response(500, json={}))
    with pytest.raises(LinearNetworkError, match="HTTP 500"):
        client.execute("query { viewer { id } }")


@respx.mock
def test_authentication_error_code(client: LinearClient) -> None:
    # HTTP 200 body, but a GraphQL auth error code -> auth error.
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(
            200,
            json={"errors": [{"message": "nope", "extensions": {"code": "AUTHENTICATION_ERROR"}}]},
        )
    )
    with pytest.raises(LinearAuthenticationError, match="nope"):
        client.execute("query { viewer { id } }")


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
    assert exc_info.value.requests_limit is None  # unparseable header -> None


@respx.mock
def test_error_without_extensions_code(client: LinearClient) -> None:
    # error code can also live at the top level of the error object
    respx.post(DEFAULT_ENDPOINT).mock(
        return_value=httpx.Response(200, json={"errors": [{"message": "boom", "code": "INTERNAL"}]})
    )
    with pytest.raises(LinearGraphQLError) as exc_info:
        client.execute("query { viewer { id } }")
    assert exc_info.value.code == "INTERNAL"


@respx.mock
def test_graphql_error_with_no_code_at_all(client: LinearClient) -> None:
    # _raise_for_errors loops every error and finds no code -> generic GraphQL error.
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

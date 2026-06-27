"""Exception types raised by the Linear client."""

from __future__ import annotations

from typing import Any


class LinearError(Exception):
    """Base class for all errors raised by ``linear_python_client``."""


class LinearAuthenticationError(LinearError):
    """Raised when the API rejects the supplied credentials.

    Triggered by HTTP 401/403 responses or GraphQL errors with codes
    ``AUTHENTICATION_ERROR``, ``UNAUTHENTICATED``, or ``FORBIDDEN``.
    """


class LinearRateLimitError(LinearError):
    """Raised when a request is rejected for exceeding a rate limit.

    Linear signals rate limiting with an HTTP 400 response whose GraphQL error
    carries the ``RATELIMITED`` code. Request-level and complexity-level
    ``X-RateLimit-*`` headers are exposed as attributes when present (otherwise
    ``None``). When an endpoint-specific limit was hit, the ``endpoint_*``
    attributes identify which limit and endpoint were exceeded.

    Attributes:
        requests_limit: Max requests allowed in the current window.
        requests_remaining: Requests left in the current window.
        requests_reset: Window reset time (UTC epoch milliseconds).
        complexity_limit: Max complexity points allowed in the current window.
        complexity_remaining: Complexity points left in the current window.
        complexity_reset: Complexity window reset time (UTC epoch milliseconds).
        query_complexity: Complexity score of the request that was rejected
            (from the ``X-Complexity`` header).
        endpoint_requests_limit: Per-endpoint request cap (when an
            endpoint-specific limit was hit).
        endpoint_requests_remaining: Requests remaining for the endpoint.
        endpoint_requests_reset: Endpoint window reset time (UTC epoch ms).
        endpoint_name: Identifies which endpoint triggered the limit.
    """

    def __init__(
        self,
        message: str,
        *,
        requests_limit: int | None = None,
        requests_remaining: int | None = None,
        requests_reset: int | None = None,
        complexity_limit: int | None = None,
        complexity_remaining: int | None = None,
        complexity_reset: int | None = None,
        query_complexity: int | None = None,
        endpoint_requests_limit: int | None = None,
        endpoint_requests_remaining: int | None = None,
        endpoint_requests_reset: int | None = None,
        endpoint_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.requests_limit = requests_limit
        self.requests_remaining = requests_remaining
        self.requests_reset = requests_reset
        self.complexity_limit = complexity_limit
        self.complexity_remaining = complexity_remaining
        self.complexity_reset = complexity_reset
        self.query_complexity = query_complexity
        self.endpoint_requests_limit = endpoint_requests_limit
        self.endpoint_requests_remaining = endpoint_requests_remaining
        self.endpoint_requests_reset = endpoint_requests_reset
        self.endpoint_name = endpoint_name


class LinearGraphQLError(LinearError):
    """Raised when the API returns one or more GraphQL ``errors``.

    The raw error list returned by the API is available as ``errors``, and the
    code of the first error carrying one (if any) is exposed via ``code``.

    Attributes:
        errors: The raw GraphQL error objects returned by the API.
    """

    def __init__(self, message: str, *, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors: list[dict[str, Any]] = errors or []

    @property
    def code(self) -> str | None:
        """The error code of the first error that carries one, else ``None``."""
        for error in self.errors:
            extensions = error.get("extensions") or {}
            code = extensions.get("code") or error.get("code")
            if code:
                return str(code)
        return None


class LinearServerError(LinearError):
    """Raised when the Linear API returns an HTTP 5xx response.

    Indicates a server-side failure unrelated to the request itself. These are
    transient in most cases; callers should back off and retry.

    Attributes:
        status_code: The HTTP status code returned (500–599).
        body_preview: Up to 300 characters of the raw response body, useful for
            diagnosing gateway or proxy errors that return non-JSON payloads.
    """

    def __init__(self, message: str, *, status_code: int, body_preview: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body_preview = body_preview


class LinearNetworkError(LinearError):
    """Raised when the request fails to reach the API or returns an unexpected response."""

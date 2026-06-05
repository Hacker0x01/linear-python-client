"""Exception types raised by the Linear client."""

from __future__ import annotations

from typing import Any


class LinearError(Exception):
    """Base class for all errors raised by ``linear_python_client``."""


class LinearAuthenticationError(LinearError):
    """Raised when the API rejects the supplied credentials (HTTP 401/403)."""


class LinearRateLimitError(LinearError):
    """Raised when a request is rejected for exceeding a rate limit.

    Linear signals rate limiting with an HTTP 400 response whose GraphQL error
    carries the `RATELIMITED` code. The relevant `X-RateLimit-*` headers are
    exposed as attributes when present (otherwise `None`).

    Attributes:
        requests_limit: Max requests allowed in the current window.
        requests_remaining: Requests left in the current window.
        requests_reset: Window reset time (UTC epoch milliseconds).
        complexity_limit: Max complexity points allowed in the current window.
        complexity_remaining: Complexity points left in the current window.
        complexity_reset: Complexity window reset time (UTC epoch milliseconds).
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
    ) -> None:
        super().__init__(message)
        self.requests_limit = requests_limit
        self.requests_remaining = requests_remaining
        self.requests_reset = requests_reset
        self.complexity_limit = complexity_limit
        self.complexity_remaining = complexity_remaining
        self.complexity_reset = complexity_reset


class LinearGraphQLError(LinearError):
    """Raised when the API returns one or more GraphQL `errors`.

    The raw error list returned by the API is available as `errors`, and the
    code of the first error carrying one (if any) is exposed via `code`.

    Attributes:
        errors: The raw GraphQL error objects returned by the API.
    """

    def __init__(self, message: str, *, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.errors: list[dict[str, Any]] = errors or []

    @property
    def code(self) -> str | None:
        """The error code of the first error that carries one, else `None`."""
        for error in self.errors:
            extensions = error.get("extensions") or {}
            code = extensions.get("code") or error.get("code")
            if code:
                return str(code)
        return None


class LinearNetworkError(LinearError):
    """Raised when the request fails to reach the API or returns an unexpected response."""

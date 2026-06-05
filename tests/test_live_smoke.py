"""Optional live smoke test against the real Linear API.

Skipped unless LINEAR_API_KEY is set in the environment. This makes a real
network request, so it does not run in normal CI / offline test runs.
"""

from __future__ import annotations

import os

import pytest

from linear_python_client import LinearClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("LINEAR_API_KEY"),
    reason="LINEAR_API_KEY not set; skipping live smoke test.",
)


def test_viewer_is_reachable() -> None:
    with LinearClient() as client:
        me = client.viewer().viewer
        assert me is not None
        assert me.id

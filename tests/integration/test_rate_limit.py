"""The rate limit on model-backed endpoints.

Cost is an attack surface when every call triggers billable inference and
nothing bounds the caller. These tests pin the two properties that matter: the
expensive endpoints are limited, and the free ones are not.
"""

from __future__ import annotations

import pytest
from argus_api.core import limits
from argus_api.core.settings import get_settings
from argus_api.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db) -> TestClient:
    limits.reset()
    with TestClient(app) as test_client:
        yield test_client
    limits.reset()


@pytest.fixture
def tiny_limit():
    """Drop the limit to something a test can reach in a few calls."""
    settings = get_settings()
    original = settings.rate_limit_per_minute
    object.__setattr__(settings, "rate_limit_per_minute", 3)
    yield 3
    object.__setattr__(settings, "rate_limit_per_minute", original)


class TestInferenceEndpointsAreLimited:
    def test_repeated_calls_are_eventually_refused(
        self, client: TestClient, tiny_limit: int
    ) -> None:
        # The case does not exist, so these 404 rather than running a model -
        # but the limiter is a route dependency and runs first regardless.
        statuses = [
            client.post("/api/cases/nope/investigations", json={}).status_code
            for _ in range(tiny_limit + 2)
        ]
        assert 429 in statuses, f"limit never enforced: {statuses}"

    def test_the_refusal_explains_itself(self, client: TestClient, tiny_limit: int) -> None:
        response = None
        for _ in range(tiny_limit + 2):
            response = client.post("/api/investigations/x/ask", json={"question": "why?"})
            if response.status_code == 429:
                break

        assert response is not None
        assert response.status_code == 429
        detail = response.json()["detail"]
        # A bare 429 tells the analyst nothing; the reason and the remedy matter.
        assert "inference" in detail
        assert "Retry-After" in response.headers


class TestReadEndpointsAreNotLimited:
    def test_reads_are_never_throttled(self, client: TestClient, tiny_limit: int) -> None:
        """Reads serve stored rows and cost nothing.

        Throttling them would degrade the interface for the analyst whose
        dashboard polls it, without saving a penny.
        """
        statuses = {client.get("/api/cases").status_code for _ in range(tiny_limit * 4)}
        assert statuses == {200}


class TestConfiguration:
    def test_a_non_positive_limit_disables_throttling(self, client: TestClient) -> None:
        settings = get_settings()
        original = settings.rate_limit_per_minute
        object.__setattr__(settings, "rate_limit_per_minute", 0)
        try:
            statuses = {
                client.post("/api/cases/nope/investigations", json={}).status_code for _ in range(8)
            }
            assert 429 not in statuses
        finally:
            object.__setattr__(settings, "rate_limit_per_minute", original)

    def test_separate_callers_get_separate_budgets(
        self, client: TestClient, tiny_limit: int
    ) -> None:
        """One caller exhausting the limit must not lock out everyone else."""
        for _ in range(tiny_limit + 2):
            client.post(
                "/api/cases/nope/investigations",
                json={},
                headers={"X-Forwarded-For": "203.0.113.1"},
            )
        other = client.post(
            "/api/cases/nope/investigations",
            json={},
            headers={"X-Forwarded-For": "203.0.113.99"},
        )
        assert other.status_code != 429

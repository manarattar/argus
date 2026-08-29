"""API contract tests.

Exercises the HTTP boundary: status codes, validation, error shapes and the
security headers. Uses FastAPI's TestClient against the real application, so
routing, dependency injection and serialisation all run for real.
"""

from __future__ import annotations

import pytest
from argus_api.main import app
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture
def client(db) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


class TestPlatformEndpoints:
    def test_health_reports_the_resolved_runtime(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        # A reviewer must always be able to tell live from replayed.
        assert body["mode"] in {"demo", "live"}

    def test_runtime_states_the_mode_in_plain_language(self, client: TestClient) -> None:
        body = client.get("/api/runtime").json()
        assert body["headline"]
        assert body["explanation"]
        assert "semantic" in body["embedding"]

    def test_dashboard_returns_zeros_rather_than_inventing_activity(
        self, client: TestClient
    ) -> None:
        body = client.get("/api/dashboard").json()
        assert body["cases"]["total"] == 0
        assert body["investigations"]["total"] == 0
        assert body["estimated_cost_usd"] == 0.0
        assert body["cost_is_estimate"] is True

    def test_architecture_is_served_from_the_running_system(self, client: TestClient) -> None:
        body = client.get("/api/architecture").json()
        assert body["capabilities"]
        assert body["controls"]
        assert body["prompts"]["prompts"]

        # The platform claim must be honest about what is actually built.
        implemented = [d for d in body["domains"] if d["implemented"]]
        design = [d for d in body["domains"] if not d["implemented"]]
        assert len(implemented) == 1
        assert design and all(d["status"] == "design" for d in design)

    def test_security_headers_are_present(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Request-ID"]


class TestValueCase:
    def test_defaults_are_documented(self, client: TestClient) -> None:
        body = client.get("/api/value-case/defaults").json()
        assert body["assumptions"]
        # Every assumption carries a note explaining it.
        for key in body["assumptions"]:
            assert key in body["notes"], f"{key} has no explanatory note"
        assert "Illustrative" in body["disclaimer"]

    def test_computes_a_result_and_sensitivity(self, client: TestClient) -> None:
        response = client.post(
            "/api/value-case",
            json={
                "cases_per_month": 100,
                "manual_hours_per_case": 6.0,
                "assisted_hours_per_case": 3.0,
                "adoption_rate": 0.8,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["result"]["monthly_hours_saved"] > 0
        assert body["sensitivity"]["series"]

    def test_rejects_inconsistent_assumptions_with_a_readable_message(
        self, client: TestClient
    ) -> None:
        response = client.post(
            "/api/value-case",
            json={"manual_hours_per_case": 2.0, "assisted_hours_per_case": 8.0},
        )
        assert response.status_code == 400
        assert "cannot exceed" in response.json()["detail"]

    def test_rejects_out_of_range_input_at_the_schema(self, client: TestClient) -> None:
        response = client.post("/api/value-case", json={"adoption_rate": 5})
        assert response.status_code == 422


class TestEvaluation:
    def test_suite_definition_is_available_before_any_run(self, client: TestClient) -> None:
        body = client.get("/api/evaluation/cases").json()
        assert body["total"] > 0
        assert body["deterministic"] > 0
        assert body["requires_model"] > 0
        assert body["deterministic"] + body["requires_model"] == body["total"]

    def test_latest_is_an_explicit_empty_state(self, client: TestClient) -> None:
        body = client.get("/api/evaluation/latest").json()
        assert body["run"] is None
        assert "No evaluation" in body["message"]

    def test_running_the_suite_reports_honest_metrics(self, client: TestClient) -> None:
        response = client.post("/api/evaluation/run", json={})
        assert response.status_code == 201
        metrics = response.json()["run"]["metrics"]

        # Skipped cases are never counted as passes.
        assert metrics["passed"] + metrics["failed"] == metrics["executed"]
        assert (
            metrics["executed"] + metrics["skipped"] + metrics["errored"]
            == (metrics["total_cases"])
        )
        assert 0.0 <= metrics["coverage"] <= 1.0

    def test_unknown_run_is_404(self, client: TestClient) -> None:
        assert client.get("/api/evaluation/runs/does-not-exist").status_code == 404


class TestCases:
    def test_empty_case_list(self, client: TestClient) -> None:
        assert client.get("/api/cases").json() == {"cases": []}

    def test_unknown_case_is_404(self, client: TestClient) -> None:
        response = client.get("/api/cases/nope")
        assert response.status_code == 404
        assert response.json()["detail"] == "Case not found."

    def test_unknown_investigation_is_404(self, client: TestClient) -> None:
        assert client.get("/api/investigations/nope/graph").status_code == 404


class TestReviewValidation:
    def test_override_requires_a_rationale_of_substance(self, client: TestClient) -> None:
        """Enforced at the schema, so a UI bug cannot bypass it."""
        response = client.patch(
            "/api/investigations/x/findings/R1/severity",
            json={"severity": "minor", "rationale": "no"},
        )
        assert response.status_code == 422

    def test_rejects_an_unknown_severity_value(self, client: TestClient) -> None:
        response = client.patch(
            "/api/investigations/x/findings/R1/severity",
            json={
                "severity": "catastrophic",
                "rationale": "a sufficiently long reason",
            },
        )
        assert response.status_code == 422

    def test_rejects_an_unknown_review_decision(self, client: TestClient) -> None:
        response = client.post(
            "/api/investigations/x/review",
            json={"decision": "rubber_stamp", "comment": "looks fine"},
        )
        assert response.status_code == 422

    def test_question_length_is_bounded(self, client: TestClient) -> None:
        response = client.post("/api/investigations/x/ask", json={"question": "a" * 5000})
        assert response.status_code == 422

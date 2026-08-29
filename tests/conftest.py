"""Shared fixtures.

The database fixture points the application at a throwaway SQLite file per test
session, so tests never touch the developer's seeded database. The provider
fixture supplies a scripted backend, which keeps agent tests deterministic and
free of network calls.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")]

from ai.providers.base import LLMProvider, LLMRequest, LLMResponse, Usage  # noqa: E402
from ai.retrieval.embeddings import HashedLexicalEmbeddings  # noqa: E402
from ai.schemas.enums import EvidenceStrength, Likelihood, RiskCategory, Severity  # noqa: E402
from ai.schemas.models import EvidenceItem, RiskFinding  # noqa: E402


class ScriptedProvider(LLMProvider):
    """Returns queued responses in order. Records every request it received.

    Used instead of mocking the HTTP layer so tests exercise the real
    structured-output path: JSON extraction, schema validation and the retry
    loop all run exactly as they do in production.
    """

    name = "scripted"
    model = "scripted-model"
    live = False

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses = list(responses or [])
        self.requests: list[LLMRequest] = []

    def queue(self, *responses: str) -> None:
        self.responses.extend(responses)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError(
                f"ScriptedProvider ran out of responses at step {request.purpose!r}"
            )
        text = self.responses.pop(0)
        return LLMResponse(
            text=text,
            model=self.model,
            usage=Usage(input_tokens=100, output_tokens=50),
            latency_ms=5,
            backend=self.name,
        )


@pytest.fixture
def scripted_provider() -> ScriptedProvider:
    return ScriptedProvider()


@pytest.fixture
def embedder() -> HashedLexicalEmbeddings:
    """The dependency-free vectoriser, so tests need no network."""
    return HashedLexicalEmbeddings(dimensions=256)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[None]:
    """Point the application at a throwaway database for one test."""
    from argus_api.db import session as session_module

    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    session_module.configure_for_tests(database_url)
    yield
    session_module._engine = None
    session_module._SessionFactory = None


def make_finding(
    *,
    risk_id: str = "R1",
    severity: Severity = Severity.MAJOR,
    likelihood: Likelihood = Likelihood.LIKELY,
    strength: EvidenceStrength = EvidenceStrength.STRONG,
    category: RiskCategory = RiskCategory.FINANCIAL,
    supporting: list[str] | None = None,
    contradicting: list[str] | None = None,
    mitigating: list[str] | None = None,
) -> RiskFinding:
    """Build a finding for scoring and uncertainty tests."""
    return RiskFinding(
        risk_id=risk_id,
        title=f"Test finding {risk_id}",
        category=category,
        description=(
            "A synthetic finding used by the test suite to exercise scoring and "
            "uncertainty behaviour deterministically."
        ),
        severity=severity,
        likelihood=likelihood,
        supporting_evidence_ids=supporting or [],
        contradicting_evidence_ids=contradicting or [],
        mitigating_factors=mitigating or [],
        evidence_strength=strength,
    )


def make_evidence(
    evidence_id: str,
    *,
    document_id: str = "doc-1",
    quote: str = "A verbatim quote from the source document.",
    grounding: float = 1.0,
) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        statement="A normalised restatement of the extracted finding.",
        quote=quote,
        category=RiskCategory.FINANCIAL,
        document_id=document_id,
        document_name="Test Document",
        section_reference="p. 1",
        chunk_id=f"{document_id}::c0",
        grounding_score=grounding,
        is_grounded=True,
    )

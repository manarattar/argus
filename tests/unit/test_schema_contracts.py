"""Identifier contracts on agent output.

These pin a class of failure found only by running the pipeline against a live
model: agents minting identifiers derived from a *location* (a chunk id) rather
than from their own sequence. Two policy clauses drawn from the same chunk then
collide, and the collision reached persistence as a primary key violation that
aborted an otherwise-complete investigation.

The fix is layered, and each layer is asserted here: the schema rejects
duplicates, and persistence is collision-proof regardless of what the schema
lets through.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai.schemas.models import (
    Challenge,
    ChallengeReport,
    ClaimVerification,
    PolicyAnalysis,
    PolicyMatch,
    VerificationReport,
)


def _match(match_id: str) -> PolicyMatch:
    return PolicyMatch(
        match_id=match_id,
        risk_id="R1",
        policy_id="policy-counterparty-risk-framework",
        clause_reference="CRF 3.2",
        clause_title="Financial assessment",
        relevance="The observed leverage exceeds the threshold stated in the clause.",
        trigger_type="threshold_met",
    )


def _challenge(challenge_id: str) -> Challenge:
    return Challenge(
        challenge_id=challenge_id,
        risk_id="R1",
        challenge_type="overstated_severity",
        argument=(
            "The cited evidence supports a narrower conclusion than the finding "
            "states, and the mitigating position is not reflected."
        ),
    )


def _verification(verification_id: str) -> ClaimVerification:
    return ClaimVerification(
        verification_id=verification_id,
        risk_id="R1",
        claim="Leverage rose materially during the period.",
        status="supported",
        reasoning="The cited borrowing figures establish the increase directly.",
    )


class TestIdentifierUniqueness:
    def test_duplicate_match_ids_are_rejected(self) -> None:
        """Two clauses from one chunk must not share an identifier."""
        with pytest.raises(ValidationError, match="match_id"):
            PolicyAnalysis(matches=[_match("M1"), _match("M1")])

    def test_distinct_match_ids_are_accepted(self) -> None:
        analysis = PolicyAnalysis(matches=[_match("M1"), _match("M2")])
        assert len(analysis.matches) == 2

    def test_duplicate_challenge_ids_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="challenge_id"):
            ChallengeReport(challenges=[_challenge("C1"), _challenge("C1")])

    def test_duplicate_verification_ids_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="verification_id"):
            VerificationReport(verifications=[_verification("V1"), _verification("V1")])


class TestPersistenceIsCollisionProof:
    def test_row_ids_include_the_ordinal(self) -> None:
        """Persistence must not depend on the schema catching duplicates.

        The row id carries the ordinal as well as the agent's identifier, so a
        model returning two records with the same id cannot abort a completed
        investigation with a primary key violation.
        """
        from argus_api.services.investigation import _persist_policy

        recorded: list[str] = []

        class _Session:
            def add(self, row: object) -> None:
                recorded.append(row.id)  # type: ignore[attr-defined]

        # Deliberately duplicated ids, as a live model produced.
        duplicates = [_match("same"), _match("same"), _match("same")]
        investigation = type("Inv", (), {"id": "inv1"})()
        _persist_policy(_Session(), investigation, duplicates)  # type: ignore[arg-type]

        assert len(recorded) == 3
        assert len(set(recorded)) == 3, "row ids collided despite duplicate match_ids"

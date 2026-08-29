"""Tests for the deterministic scoring engine.

These pin the arithmetic behind the most consequential number in the product.
The properties asserted here are the ones the design actually claims, in
particular that weak evidence cannot drive a high rating and that missing
information is treated conservatively rather than as reassurance.
"""

from __future__ import annotations

import pytest

from ai.schemas.enums import (
    CoverageStatus,
    EvidenceStrength,
    Likelihood,
    RiskCategory,
    RiskLevel,
    Severity,
)
from ai.schemas.models import ClaimVerification, CoverageItem, PolicyMatch
from ai.scoring.engine import (
    EVIDENCE_MULTIPLIER,
    adjusted_score,
    categories_in_scope,
    compute_assessment_score,
    inherent_score,
)
from tests.conftest import make_finding


def coverage(*statuses: CoverageStatus) -> list[CoverageItem]:
    return [
        CoverageItem(
            category=list(RiskCategory)[index],
            status=status,
            expected="expected evidence for this category",
        )
        for index, status in enumerate(statuses)
    ]


class TestInherentScore:
    def test_multiplies_severity_by_likelihood(self) -> None:
        finding = make_finding(severity=Severity.SEVERE, likelihood=Likelihood.ALMOST_CERTAIN)
        assert inherent_score(finding) == 25.0

    def test_lowest_possible_score_is_one(self) -> None:
        finding = make_finding(severity=Severity.NEGLIGIBLE, likelihood=Likelihood.RARE)
        assert inherent_score(finding) == 1.0

    @pytest.mark.parametrize(
        ("strength", "expected"),
        [
            (EvidenceStrength.STRONG, 20.0),
            (EvidenceStrength.MODERATE, 16.4),
            (EvidenceStrength.WEAK, 11.0),
            (EvidenceStrength.INSUFFICIENT, 5.0),
        ],
    )
    def test_evidence_discounts_the_inherent_score(
        self, strength: EvidenceStrength, expected: float
    ) -> None:
        finding = make_finding(
            severity=Severity.SEVERE, likelihood=Likelihood.LIKELY, strength=strength
        )
        assert adjusted_score(finding) == pytest.approx(expected)


class TestOverallRating:
    def test_severe_well_evidenced_finding_reaches_high(self) -> None:
        """The engine's core promise: a serious, well-evidenced risk can drive
        the rating on its own, without needing a policy breach to get there."""
        result = compute_assessment_score(
            [
                make_finding(severity=Severity.SEVERE, likelihood=Likelihood.LIKELY),
                make_finding(
                    risk_id="R2",
                    severity=Severity.MAJOR,
                    likelihood=Likelihood.POSSIBLE,
                    category=RiskCategory.GOVERNANCE,
                ),
            ],
            coverage=coverage(CoverageStatus.COMPLETE, CoverageStatus.COMPLETE),
        )
        assert result.overall_level is RiskLevel.HIGH

    def test_weak_evidence_cannot_produce_a_high_rating(self) -> None:
        """The anti-hallucination property, expressed as arithmetic.

        The same severe, near-certain finding drops out of High once its
        evidence is insufficient - a model cannot talk its way to a high rating.
        """
        strong = compute_assessment_score(
            [make_finding(severity=Severity.SEVERE, likelihood=Likelihood.ALMOST_CERTAIN)],
            coverage=coverage(CoverageStatus.COMPLETE),
        )
        weak = compute_assessment_score(
            [
                make_finding(
                    severity=Severity.SEVERE,
                    likelihood=Likelihood.ALMOST_CERTAIN,
                    strength=EvidenceStrength.INSUFFICIENT,
                )
            ],
            coverage=coverage(CoverageStatus.COMPLETE),
        )
        assert strong.overall_level is RiskLevel.HIGH
        assert weak.overall_level.ordinal < RiskLevel.HIGH.ordinal
        assert weak.overall_score < strong.overall_score

    def test_minor_unlikely_findings_stay_low(self) -> None:
        result = compute_assessment_score(
            [make_finding(severity=Severity.MINOR, likelihood=Likelihood.UNLIKELY)],
            coverage=coverage(CoverageStatus.COMPLETE),
        )
        assert result.overall_level is RiskLevel.LOW

    def test_no_findings_is_reported_not_errored(self) -> None:
        result = compute_assessment_score([])
        assert result.overall_level is RiskLevel.LOW
        assert result.overall_score == 0.0
        assert result.factors[0].key == "no_findings"
        # The empty case must still explain itself rather than render blank.
        assert "reviewed" in result.factors[0].detail

    def test_score_is_bounded(self) -> None:
        findings = [
            make_finding(
                risk_id=f"R{index}",
                severity=Severity.SEVERE,
                likelihood=Likelihood.ALMOST_CERTAIN,
                category=category,
            )
            for index, category in enumerate(list(RiskCategory)[:6])
        ]
        matches = [
            PolicyMatch(
                match_id=f"M{index}",
                risk_id=f"R{index}",
                policy_id="policy",
                clause_reference=f"CRF {index}.1",
                clause_title="Clause",
                relevance="Relevant to the finding under assessment in this test.",
                trigger_type="potential_breach",
            )
            for index in range(6)
        ]
        result = compute_assessment_score(
            findings,
            policy_matches=matches,
            coverage=coverage(*[CoverageStatus.MISSING] * 6),
        )
        assert 0.0 <= result.overall_score <= 100.0


class TestFactors:
    def test_mitigating_factors_reduce_the_score(self) -> None:
        without = compute_assessment_score(
            [make_finding()], coverage=coverage(CoverageStatus.COMPLETE)
        )
        with_mitigation = compute_assessment_score(
            [make_finding(mitigating=["a", "b", "c", "d", "e", "f"])],
            coverage=coverage(CoverageStatus.COMPLETE),
        )
        assert with_mitigation.overall_score < without.overall_score

    def test_missing_coverage_raises_rather_than_lowers_the_score(self) -> None:
        """Unknowns are scored conservatively. A thin file must not read as a
        clean one - the opposite behaviour would be actively dangerous."""
        complete = compute_assessment_score(
            [make_finding()], coverage=coverage(CoverageStatus.COMPLETE)
        )
        incomplete = compute_assessment_score(
            [make_finding()], coverage=coverage(CoverageStatus.MISSING)
        )
        assert incomplete.overall_score > complete.overall_score

    def test_unverified_claims_drag_the_score_down(self) -> None:
        verifications = [
            ClaimVerification(
                verification_id="V1",
                risk_id="R1",
                claim="The claim under verification for this test case.",
                status="unsupported",
                reasoning="The cited evidence does not establish the claim as stated.",
            )
        ]
        without = compute_assessment_score(
            [make_finding()], coverage=coverage(CoverageStatus.COMPLETE)
        )
        with_drag = compute_assessment_score(
            [make_finding()],
            verifications=verifications,
            coverage=coverage(CoverageStatus.COMPLETE),
        )
        assert with_drag.overall_score < without.overall_score

    def test_every_factor_has_an_explanation(self) -> None:
        """A factor without a detail string would render as an unexplained
        number, which defeats the purpose of showing factors at all."""
        result = compute_assessment_score(
            [make_finding()], coverage=coverage(CoverageStatus.PARTIAL)
        )
        for factor in result.factors:
            assert factor.label
            assert factor.detail
            assert factor.direction in {"increases", "decreases", "neutral"}

    def test_factors_sum_to_the_score(self) -> None:
        result = compute_assessment_score(
            [
                make_finding(),
                make_finding(risk_id="R2", category=RiskCategory.GOVERNANCE),
            ],
            coverage=coverage(CoverageStatus.COMPLETE, CoverageStatus.PARTIAL),
        )
        total = sum(factor.contribution for factor in result.factors)
        assert result.overall_score == pytest.approx(max(0.0, min(100.0, total)), abs=0.05)


class TestCategoryLevels:
    def test_worst_finding_sets_the_category_level(self) -> None:
        result = compute_assessment_score(
            [
                make_finding(risk_id="R1", severity=Severity.MINOR, likelihood=Likelihood.RARE),
                make_finding(risk_id="R2", severity=Severity.SEVERE, likelihood=Likelihood.LIKELY),
            ],
            coverage=coverage(CoverageStatus.COMPLETE),
        )
        assert result.category_levels[RiskCategory.FINANCIAL.value] is RiskLevel.HIGH

    def test_categories_in_scope_follows_taxonomy_order(self) -> None:
        findings = [
            make_finding(risk_id="R1", category=RiskCategory.GOVERNANCE),
            make_finding(risk_id="R2", category=RiskCategory.FINANCIAL),
        ]
        assert categories_in_scope(findings) == [
            RiskCategory.FINANCIAL,
            RiskCategory.GOVERNANCE,
        ]


def test_evidence_multiplier_is_monotonic() -> None:
    """Stronger evidence must never survive worse than weaker evidence."""
    ordered = [
        EvidenceStrength.INSUFFICIENT,
        EvidenceStrength.WEAK,
        EvidenceStrength.MODERATE,
        EvidenceStrength.STRONG,
    ]
    values = [EVIDENCE_MULTIPLIER[band] for band in ordered]
    assert values == sorted(values)

"""Tests for the uncertainty model, coverage, escalation and the value case."""

from __future__ import annotations

import pytest
from argus_api.services.value_case import ValueAssumptions, compute, sensitivity

from ai.domain import COUNTERPARTY_REVIEW, get_domain, list_domains
from ai.schemas.enums import (
    CoverageStatus,
    EvidenceKind,
    EvidenceStrength,
    Likelihood,
    RiskCategory,
    RiskLevel,
    Severity,
    SupportStatus,
)
from ai.schemas.models import PolicyMatch
from ai.scoring.coverage import assess_coverage, coverage_ratio, evaluate_escalation
from ai.scoring.uncertainty import assess_evidence_strength
from tests.conftest import make_evidence, make_finding


class TestEvidenceStrength:
    def test_no_usable_citations_is_insufficient(self) -> None:
        finding = make_finding(supporting=["MISSING"])
        result = assess_evidence_strength(finding, {})
        assert result.strength is EvidenceStrength.INSUFFICIENT
        assert result.score == 0.0
        assert "no cited evidence" in result.rationale.lower()

    def test_verifier_rejection_forces_insufficient(self) -> None:
        """A hard rule, not a weight: four citations cannot rescue a claim the
        verifier says its citations do not support."""
        evidence = {f"E{i}": make_evidence(f"E{i}", document_id=f"d{i}") for i in range(1, 5)}
        finding = make_finding(supporting=list(evidence))
        result = assess_evidence_strength(
            finding, evidence, verifier_status=SupportStatus.UNSUPPORTED
        )
        assert result.strength is EvidenceStrength.INSUFFICIENT

    def test_corroboration_across_documents_reaches_strong(self) -> None:
        evidence = {
            "E1": make_evidence("E1", document_id="d1"),
            "E2": make_evidence("E2", document_id="d2"),
            "E3": make_evidence("E3", document_id="d2"),
        }
        finding = make_finding(supporting=["E1", "E2", "E3"])
        result = assess_evidence_strength(
            finding, evidence, verifier_status=SupportStatus.SUPPORTED
        )
        assert result.strength is EvidenceStrength.STRONG

    def test_independent_sources_beat_repetition(self) -> None:
        """Three quotes from one document are one source, not three."""
        same_document = {f"E{i}": make_evidence(f"E{i}", document_id="d1") for i in range(1, 4)}
        spread = {f"E{i}": make_evidence(f"E{i}", document_id=f"d{i}") for i in range(1, 4)}
        finding = make_finding(supporting=["E1", "E2", "E3"])

        concentrated = assess_evidence_strength(finding, same_document)
        distributed = assess_evidence_strength(finding, spread)
        assert distributed.score > concentrated.score

    def test_contradicting_evidence_lowers_the_band(self) -> None:
        evidence = {f"E{i}": make_evidence(f"E{i}", document_id=f"d{i}") for i in range(1, 5)}
        uncontested = assess_evidence_strength(make_finding(supporting=["E1", "E2"]), evidence)
        contested = assess_evidence_strength(
            make_finding(supporting=["E1", "E2"], contradicting=["E3", "E4"]),
            evidence,
            verifier_status=SupportStatus.CONFLICTING,
        )
        assert contested.score < uncontested.score

    def test_every_signal_is_explained(self) -> None:
        evidence = {"E1": make_evidence("E1")}
        result = assess_evidence_strength(make_finding(supporting=["E1"]), evidence)
        assert result.rationale
        for signal in result.signals:
            assert signal.label and signal.detail

    def test_score_stays_in_range(self) -> None:
        evidence = {f"E{i}": make_evidence(f"E{i}", document_id=f"d{i}") for i in range(1, 9)}
        result = assess_evidence_strength(
            make_finding(supporting=list(evidence)),
            evidence,
            verifier_status=SupportStatus.SUPPORTED,
        )
        assert 0.0 <= result.score <= 1.0


class TestCoverage:
    def test_only_facts_count_toward_coverage(self) -> None:
        """A category supported only by the model's own interpretations has not
        actually been evidenced."""
        interpretations = [
            make_evidence("E1").model_copy(update={"kind": EvidenceKind.INTERPRETATION}),
            make_evidence("E2").model_copy(update={"kind": EvidenceKind.INTERPRETATION}),
        ]
        result = assess_coverage(COUNTERPARTY_REVIEW, interpretations)
        financial = next(c for c in result if c.category is RiskCategory.FINANCIAL)
        assert financial.status is CoverageStatus.PARTIAL

    def test_two_facts_make_a_category_complete(self) -> None:
        facts = [
            make_evidence("E1", document_id="d1"),
            make_evidence("E2", document_id="d2"),
        ]
        result = assess_coverage(COUNTERPARTY_REVIEW, facts)
        financial = next(c for c in result if c.category is RiskCategory.FINANCIAL)
        assert financial.status is CoverageStatus.COMPLETE

    def test_absent_category_is_missing_with_a_reason(self) -> None:
        result = assess_coverage(COUNTERPARTY_REVIEW, [])
        assert all(item.status is CoverageStatus.MISSING for item in result)
        assert all(item.note for item in result)

    def test_ratio_reflects_completeness(self) -> None:
        assert coverage_ratio([]) == 0.0
        facts = [
            make_evidence("E1", document_id="d1"),
            make_evidence("E2", document_id="d2"),
        ]
        result = assess_coverage(COUNTERPARTY_REVIEW, facts)
        assert 0.0 < coverage_ratio(result) < 1.0


class TestEscalation:
    def test_high_rating_escalates(self) -> None:
        reasons = evaluate_escalation(COUNTERPARTY_REVIEW, [make_finding()], [], RiskLevel.HIGH)
        assert any("High" in reason for reason in reasons)

    def test_potential_breach_escalates_at_any_rating(self) -> None:
        match = PolicyMatch(
            match_id="M1",
            risk_id="R1",
            policy_id="policy",
            clause_reference="TRA 5.2",
            clause_title="Third-party technology risk",
            relevance="Suppliers hold access and no assessment process exists.",
            trigger_type="potential_breach",
        )
        reasons = evaluate_escalation(
            COUNTERPARTY_REVIEW, [make_finding()], [match], RiskLevel.MODERATE
        )
        assert any("breach" in reason.lower() for reason in reasons)

    def test_material_finding_on_thin_evidence_escalates(self) -> None:
        """The evidential gap, not the rating, is the decision-relevant fact."""
        finding = make_finding(severity=Severity.SEVERE, strength=EvidenceStrength.WEAK)
        reasons = evaluate_escalation(COUNTERPARTY_REVIEW, [finding], [], RiskLevel.MODERATE)
        assert any("thin evidence" in reason.lower() for reason in reasons)

    def test_well_evidenced_moderate_case_does_not_escalate(self) -> None:
        finding = make_finding(
            severity=Severity.MODERATE,
            likelihood=Likelihood.POSSIBLE,
            strength=EvidenceStrength.STRONG,
        )
        assert evaluate_escalation(COUNTERPARTY_REVIEW, [finding], [], RiskLevel.MODERATE) == []


class TestDomainConfiguration:
    def test_default_domain_is_the_implemented_one(self) -> None:
        assert get_domain().key == "counterparty_review"
        assert get_domain().implemented

    def test_design_domains_are_marked_unimplemented(self) -> None:
        """The platform claim is only honest if unbuilt domains say so."""
        design = [d for d in list_domains() if not d.implemented]
        assert design
        assert all(d.status == "design" for d in design)

    def test_unknown_domain_raises_with_a_useful_message(self) -> None:
        with pytest.raises(ValueError, match="Known domains"):
            get_domain("not_a_domain")

    def test_implemented_domain_declares_its_expectations(self) -> None:
        domain = get_domain()
        assert domain.expected_evidence
        assert domain.escalation_rules
        assert domain.policy_library


class TestValueCase:
    def test_defaults_produce_a_positive_case(self) -> None:
        result = compute(ValueAssumptions())
        assert result.monthly_hours_saved > 0
        assert result.break_even_months is not None

    def test_adoption_rate_scales_the_benefit(self) -> None:
        """A tool nobody uses saves nothing - the model has to reflect that."""
        full = compute(ValueAssumptions(adoption_rate=1.0))
        partial = compute(ValueAssumptions(adoption_rate=0.5))
        none = compute(ValueAssumptions(adoption_rate=0.0))
        assert full.monthly_hours_saved > partial.monthly_hours_saved > 0
        assert none.monthly_hours_saved == 0

    def test_no_saving_when_assisted_equals_manual(self) -> None:
        result = compute(ValueAssumptions(manual_hours_per_case=6.0, assisted_hours_per_case=6.0))
        assert result.monthly_hours_saved == 0
        assert result.break_even_months is None

    def test_rejects_inconsistent_assumptions(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            compute(ValueAssumptions(manual_hours_per_case=3.0, assisted_hours_per_case=6.0))

    def test_rejects_impossible_adoption_rate(self) -> None:
        with pytest.raises(ValueError, match="between 0 and 1"):
            compute(ValueAssumptions(adoption_rate=1.5))

    def test_sensitivity_produces_a_series_around_the_base(self) -> None:
        analysis = sensitivity(ValueAssumptions(), variable="adoption_rate")
        assert len(analysis["series"]) > 1
        assert analysis["base_value"] == pytest.approx(0.7)

    def test_sensitivity_rejects_unknown_variable(self) -> None:
        with pytest.raises(ValueError, match="Unknown assumption"):
            sensitivity(ValueAssumptions(), variable="not_a_field")

    def test_disclaimer_is_always_attached(self) -> None:
        assert "Illustrative" in compute(ValueAssumptions()).disclaimer

"""Investigation completeness and deterministic escalation.

Coverage answers a question the risk rating cannot: *did we actually look at
everything this review is supposed to cover?* A confident assessment built on
half a file is more dangerous than an uncertain one built on a complete file,
because the reader has no way to tell them apart from the rating alone.

Coverage is measured against the domain's declared expectations
(:class:`~ai.domain.ExpectedEvidence`), not against what the model happened to
produce. Measuring against the model's own output would make "complete" mean
nothing more than "the model stopped".

Escalation is likewise computed from rules held as domain data, never inferred
by a model. A control that depends on a model choosing to honour it is not a
control.
"""

from __future__ import annotations

from ai.domain import DomainConfig
from ai.schemas.enums import CoverageStatus, EvidenceKind, EvidenceStrength, RiskLevel, Severity
from ai.schemas.models import CoverageItem, EvidenceItem, PolicyMatch, RiskFinding

# A category needs more than a single passing mention before it counts as
# properly covered.
COMPLETE_THRESHOLD = 2

# Severities serious enough that thin evidence becomes a reason to escalate
# rather than a reason to discount the finding.
MATERIAL_SEVERITIES = frozenset({Severity.MAJOR, Severity.SEVERE})
THIN_EVIDENCE = frozenset({EvidenceStrength.WEAK, EvidenceStrength.INSUFFICIENT})


def assess_coverage(domain: DomainConfig, evidence: list[EvidenceItem]) -> list[CoverageItem]:
    """Grade how completely each expected evidence category was satisfied.

    Only ``fact`` evidence counts toward coverage. A category supported solely
    by the model's own interpretations has not actually been evidenced, and
    treating it as covered would defeat the purpose of the check.

    Args:
        domain: Configuration declaring what a complete file contains.
        evidence: Grounded evidence extracted for the case.

    Returns:
        One :class:`CoverageItem` per expected evidence category.
    """
    items: list[CoverageItem] = []

    for expected in domain.expected_evidence:
        matching = [e for e in evidence if e.category == expected.category]
        factual = [e for e in matching if e.kind is EvidenceKind.FACT]

        if len(factual) >= COMPLETE_THRESHOLD:
            status = CoverageStatus.COMPLETE
            note = (
                f"{len(factual)} factual item(s) across "
                f"{len({e.document_id for e in factual})} document(s)."
            )
        elif matching:
            status = CoverageStatus.PARTIAL
            note = f"Only {len(factual)} factual item(s) found" + (
                f" alongside {len(matching) - len(factual)} interpretation(s)."
                if len(matching) > len(factual)
                else "."
            )
        else:
            status = CoverageStatus.MISSING
            note = "No evidence found for this category. " + (
                "This is required for a complete review."
                if expected.required
                else "This category is optional for this review type."
            )

        items.append(
            CoverageItem(
                category=expected.category,
                status=status,
                expected=expected.description,
                found_evidence_ids=[e.evidence_id for e in matching],
                note=note,
            )
        )

    return items


def coverage_ratio(coverage: list[CoverageItem]) -> float:
    """Fraction of expected categories fully covered, for dashboard reporting."""
    if not coverage:
        return 0.0
    complete = sum(1 for c in coverage if c.status is CoverageStatus.COMPLETE)
    return round(complete / len(coverage), 3)


def evaluate_escalation(
    domain: DomainConfig,
    findings: list[RiskFinding],
    policy_matches: list[PolicyMatch],
    overall_level: RiskLevel,
) -> list[str]:
    """Apply the domain's escalation rules to a completed assessment.

    Returns:
        Human-readable reasons, one per rule that fired. An empty list means no
        rule requires senior review - not that the assessment is approved.
    """
    reasons: list[str] = []
    rules = {rule.key: rule for rule in domain.escalation_rules}

    if "high_overall" in rules and overall_level is RiskLevel.HIGH:
        reasons.append(
            f"{rules['high_overall'].label}: provisional rating is " f"{overall_level.label}."
        )

    if "potential_breach" in rules:
        breaches = [m for m in policy_matches if m.trigger_type == "potential_breach"]
        if breaches:
            clauses = ", ".join(sorted({m.clause_reference for m in breaches}))
            reasons.append(
                f"{rules['potential_breach'].label}: {len(breaches)} potential "
                f"breach(es) identified against {clauses}."
            )

    if "insufficient_evidence_material_risk" in rules:
        thin = [
            f
            for f in findings
            if f.severity in MATERIAL_SEVERITIES and f.evidence_strength in THIN_EVIDENCE
        ]
        if thin:
            titles = "; ".join(f.title for f in thin[:3])
            reasons.append(
                f"{rules['insufficient_evidence_material_risk'].label}: "
                f"{len(thin)} material finding(s) rest on thin evidence ({titles})."
            )

    return reasons

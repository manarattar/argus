"""Deterministic risk scoring.

The overall rating is the most consequential number ARGUS produces, so a
language model is not allowed to author it. The model contributes *ordinal
judgements* it is reasonably good at - how severe a finding is, how likely, what
evidence bears on it - and this module combines them with arithmetic a risk
committee could audit on paper.

Why this split matters
----------------------
An LLM asked directly for "Low/Moderate/Elevated/High" produces a label that
cannot be interrogated: it is unstable across runs, sensitive to prompt
phrasing, and impossible to reconcile with the underlying findings. Computing
the label instead buys four properties the enterprise setting requires:

* **Reproducibility** - identical findings always produce an identical rating.
* **Explainability** - every point is attributable to a named factor.
* **Testability** - the rules are ordinary unit tests.
* **Governability** - thresholds are policy parameters a risk function can tune
  without retraining or re-prompting anything.

The model shapes the inputs; the institution owns the function.

Scoring model
-------------
Each finding gets an *inherent* score (severity x likelihood, 1..25) which is
then discounted by how well the evidence actually supports it. Weak evidence
cannot drive a high rating - that is the anti-hallucination property expressed
in arithmetic.

Those adjusted scores roll up through seven named factors, listed in
``LEVEL_THRESHOLDS`` order and documented in docs/architecture/scoring.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai.schemas.enums import (
    CoverageStatus,
    EvidenceStrength,
    RiskCategory,
    RiskLevel,
    Severity,
    SupportStatus,
)
from ai.schemas.models import (
    Challenge,
    ClaimVerification,
    CoverageItem,
    PolicyMatch,
    RiskFinding,
    ScoreFactor,
)

# How much of a finding's inherent score survives, given its evidence band.
# Weak evidence cannot produce a high rating - the central control of the model.
EVIDENCE_MULTIPLIER: dict[EvidenceStrength, float] = {
    EvidenceStrength.STRONG: 1.00,
    EvidenceStrength.MODERATE: 0.82,
    EvidenceStrength.WEAK: 0.55,
    EvidenceStrength.INSUFFICIENT: 0.25,
}

# A category counts toward "breadth" once its adjusted score clears this bar.
MATERIALITY_THRESHOLD = 6.0

# Weight ceilings for each factor. The findings themselves carry most of the
# score; policy, coverage and the review outcomes modify it. An earlier
# calibration split the weight evenly across all factors, which made it
# arithmetically impossible for a severe, well-evidenced, uncontested finding to
# produce a High rating without also breaching a policy clause - a result the
# evaluation suite caught (cases sco-001, sco-002, sco-004) and which
# contradicted this module's own stated design.
PEAK_WEIGHT = 75.0
BREADTH_WEIGHT = 15.0
POLICY_WEIGHT = 10.0
GAP_WEIGHT = 8.0
UNSUBSTANTIATED_WEIGHT = 8.0
MITIGATION_WEIGHT = 12.0
VERIFICATION_WEIGHT = 12.0
CONTESTED_WEIGHT = 6.0

# Severities serious enough that thin evidence is itself decision-relevant,
# per the escalation principle in CRF 7.3.
_MATERIAL_SEVERITIES = frozenset({Severity.MAJOR, Severity.SEVERE})
_THIN_EVIDENCE = frozenset({EvidenceStrength.WEAK, EvidenceStrength.INSUFFICIENT})

# Policy trigger types that indicate a real threshold event rather than context.
ESCALATING_TRIGGERS = frozenset({"potential_breach", "threshold_met", "review_trigger"})

# Band edges for the 0-100 composite. A risk function would own these values.
LEVEL_THRESHOLDS: tuple[tuple[float, RiskLevel], ...] = (
    (66.0, RiskLevel.HIGH),
    (46.0, RiskLevel.ELEVATED),
    (26.0, RiskLevel.MODERATE),
)

MAX_INHERENT = 25.0


@dataclass(frozen=True)
class ScoredFinding:
    """A finding with its computed inherent and evidence-adjusted scores."""

    finding: RiskFinding
    inherent: float
    adjusted: float


@dataclass(frozen=True)
class ScoreResult:
    """Complete, explainable output of the scoring engine."""

    overall_score: float
    overall_level: RiskLevel
    factors: list[ScoreFactor]
    category_levels: dict[str, RiskLevel]
    scored_findings: list[ScoredFinding]
    portfolio_strength: EvidenceStrength


def inherent_score(finding: RiskFinding) -> float:
    """Severity x likelihood on a 1..25 scale."""
    return float(finding.severity.ordinal * finding.likelihood.ordinal)


def adjusted_score(finding: RiskFinding) -> float:
    """Inherent score discounted by how well the evidence carries the finding."""
    return round(inherent_score(finding) * EVIDENCE_MULTIPLIER[finding.evidence_strength], 3)


def _level_from_adjusted(adjusted: float) -> RiskLevel:
    """Map a single finding's adjusted score onto the shared four-point scale."""
    if adjusted >= 15.0:
        return RiskLevel.HIGH
    if adjusted >= 9.0:
        return RiskLevel.ELEVATED
    if adjusted >= 4.0:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_assessment_score(
    findings: list[RiskFinding],
    *,
    policy_matches: list[PolicyMatch] | None = None,
    verifications: list[ClaimVerification] | None = None,
    challenges: list[Challenge] | None = None,
    coverage: list[CoverageItem] | None = None,
) -> ScoreResult:
    """Combine findings and their checks into an explainable 0-100 rating.

    Args:
        findings: Risk findings, already annotated with ``evidence_strength``
            by :mod:`ai.scoring.uncertainty`.
        policy_matches: Clause matches from the Policy Analyst.
        verifications: Verdicts from the Evidence Verifier.
        challenges: Arguments raised by the Challenger.
        coverage: Investigation-completeness entries.

    Returns:
        A :class:`ScoreResult` carrying the rating and every factor behind it.
    """
    policy_matches = policy_matches or []
    verifications = verifications or []
    challenges = challenges or []
    coverage = coverage or []

    scored = [
        ScoredFinding(finding=f, inherent=inherent_score(f), adjusted=adjusted_score(f))
        for f in findings
    ]

    if not scored:
        return _empty_result(coverage)

    factors: list[ScoreFactor] = []
    ranked = sorted(scored, key=lambda s: s.adjusted, reverse=True)

    # --- Factor 1: peak risk ----------------------------------------------
    peak = ranked[0]
    peak_points = (peak.adjusted / MAX_INHERENT) * PEAK_WEIGHT
    factors.append(
        ScoreFactor(
            key="peak_risk",
            label="Highest evidence-adjusted risk",
            detail=(
                f"'{peak.finding.title}' scores {peak.adjusted:.1f}/25 "
                f"({peak.finding.severity.label} severity x "
                f"{peak.finding.likelihood.label} likelihood, discounted for "
                f"{peak.finding.evidence_strength.label.lower()})."
            ),
            contribution=round(peak_points, 2),
            direction="increases",
        )
    )

    # --- Factor 2: breadth -------------------------------------------------
    material_categories = {
        s.finding.category for s in scored if s.adjusted >= MATERIALITY_THRESHOLD
    }
    breadth_points = (min(len(material_categories), 3) / 3) * BREADTH_WEIGHT
    named = ", ".join(sorted(c.label for c in material_categories)) or "none"
    factors.append(
        ScoreFactor(
            key="risk_breadth",
            label="Breadth across risk categories",
            detail=(
                f"{len(material_categories)} categor"
                f"{'y' if len(material_categories) == 1 else 'ies'} carry a material "
                f"finding: {named}."
            ),
            contribution=round(breadth_points, 2),
            direction="increases" if breadth_points else "neutral",
        )
    )

    # --- Factor 3: policy triggers ----------------------------------------
    triggered = [m for m in policy_matches if m.trigger_type in ESCALATING_TRIGGERS]
    trigger_points = (min(len(triggered), 3) / 3) * POLICY_WEIGHT
    trigger_refs = ", ".join(sorted({m.clause_reference for m in triggered})[:4])
    factors.append(
        ScoreFactor(
            key="policy_triggers",
            label="Internal policy triggers",
            detail=(
                f"{len(triggered)} policy clause(s) triggered"
                + (f": {trigger_refs}." if trigger_refs else ".")
            ),
            contribution=round(trigger_points, 2),
            direction="increases" if trigger_points else "neutral",
        )
    )

    # --- Factor 4: unknowns treated conservatively ------------------------
    missing = [c for c in coverage if c.status is not CoverageStatus.COMPLETE]
    missing_ratio = (len(missing) / len(coverage)) if coverage else 0.0
    unknown_points = missing_ratio * GAP_WEIGHT
    factors.append(
        ScoreFactor(
            key="information_gaps",
            label="Incomplete evidence coverage",
            detail=(
                f"{len(missing)} of {len(coverage)} expected evidence categor"
                f"{'y is' if len(coverage) == 1 else 'ies are'} partial or missing. "
                "Unknowns are scored conservatively rather than read as reassurance."
            ),
            contribution=round(unknown_points, 2),
            direction="increases" if unknown_points else "neutral",
        )
    )

    # --- Factor 5: material claims resting on thin evidence ---------------
    # CRF 7.3: where a Major or Severe finding rests on weak or insufficient
    # evidence, the evidential gap is itself decision-relevant. Discounting the
    # finding to nothing would let a serious but unproven claim disappear
    # quietly, which is the opposite of what a reviewer needs.
    unsubstantiated = [
        s
        for s in scored
        if s.finding.severity in _MATERIAL_SEVERITIES
        and s.finding.evidence_strength in _THIN_EVIDENCE
    ]
    unsubstantiated_points = (min(len(unsubstantiated), 2) / 2) * UNSUBSTANTIATED_WEIGHT
    factors.append(
        ScoreFactor(
            key="unsubstantiated_material_claims",
            label="Material findings on thin evidence",
            detail=(
                f"{len(unsubstantiated)} finding(s) of Major or Severe severity rest "
                "on weak or insufficient evidence. The gap is treated as "
                "decision-relevant rather than as grounds to discount the finding."
            ),
            contribution=round(unsubstantiated_points, 2),
            direction="increases" if unsubstantiated_points else "neutral",
        )
    )

    # --- Factor 5: evidenced mitigation -----------------------------------
    mitigation_count = sum(len(s.finding.mitigating_factors) for s in scored)
    mitigation_points = -(min(mitigation_count, 6) / 6) * MITIGATION_WEIGHT
    factors.append(
        ScoreFactor(
            key="mitigation",
            label="Documented mitigating factors",
            detail=(
                f"{mitigation_count} mitigating factor(s) recorded against findings, "
                "each traceable to case evidence."
            ),
            contribution=round(mitigation_points, 2),
            direction="decreases" if mitigation_points else "neutral",
        )
    )

    # --- Factor 6: verification drag --------------------------------------
    weak_statuses = {SupportStatus.UNSUPPORTED, SupportStatus.PARTIALLY_SUPPORTED}
    unverified = [v for v in verifications if v.status in weak_statuses]
    unverified_ratio = (len(unverified) / len(verifications)) if verifications else 0.0
    verification_points = -unverified_ratio * VERIFICATION_WEIGHT
    factors.append(
        ScoreFactor(
            key="verification_drag",
            label="Claims the verifier could not fully stand behind",
            detail=(
                f"{len(unverified)} of {len(verifications)} checked claim(s) came back "
                "partially supported or unsupported, so they cannot hold the rating up."
            ),
            contribution=round(verification_points, 2),
            direction="decreases" if verification_points else "neutral",
        )
    )

    # --- Factor 7: unresolved challenges ----------------------------------
    unresolved = [c for c in challenges if c.unresolved]
    challenge_points = -(min(len(unresolved), 3) / 3) * CONTESTED_WEIGHT
    factors.append(
        ScoreFactor(
            key="contested_findings",
            label="Unresolved challenges",
            detail=(
                f"{len(unresolved)} challenge(s) remain unresolved on the evidence "
                "available, so the associated findings are held with less conviction."
            ),
            contribution=round(challenge_points, 2),
            direction="decreases" if challenge_points else "neutral",
        )
    )

    total = _clamp(sum(f.contribution for f in factors), 0.0, 100.0)
    level = next(
        (lvl for threshold, lvl in LEVEL_THRESHOLDS if total >= threshold),
        RiskLevel.LOW,
    )

    return ScoreResult(
        overall_score=round(total, 2),
        overall_level=level,
        factors=factors,
        category_levels=_category_levels(scored),
        scored_findings=scored,
        portfolio_strength=_portfolio_strength(scored),
    )


def _category_levels(scored: list[ScoredFinding]) -> dict[str, RiskLevel]:
    """Worst adjusted finding sets the level for its category."""
    levels: dict[str, RiskLevel] = {}
    for item in scored:
        key = item.finding.category.value
        candidate = _level_from_adjusted(item.adjusted)
        if key not in levels or candidate.ordinal > levels[key].ordinal:
            levels[key] = candidate
    return levels


def _portfolio_strength(scored: list[ScoredFinding]) -> EvidenceStrength:
    """Evidence strength of the assessment as a whole.

    Weighted toward the findings that actually drive the rating: a well-evidenced
    trivial finding should not make a poorly-evidenced severe one look solid.
    """
    if not scored:
        return EvidenceStrength.INSUFFICIENT
    weights = [max(s.adjusted, 0.5) for s in scored]
    weighted = sum(
        s.finding.evidence_strength.ordinal * w for s, w in zip(scored, weights, strict=True)
    )
    mean_ordinal = weighted / sum(weights)
    if mean_ordinal >= 3.5:
        return EvidenceStrength.STRONG
    if mean_ordinal >= 2.6:
        return EvidenceStrength.MODERATE
    if mean_ordinal >= 1.6:
        return EvidenceStrength.WEAK
    return EvidenceStrength.INSUFFICIENT


def _empty_result(coverage: list[CoverageItem]) -> ScoreResult:
    """No findings is a meaningful outcome, not an error - report it as such."""
    return ScoreResult(
        overall_score=0.0,
        overall_level=RiskLevel.LOW,
        factors=[
            ScoreFactor(
                key="no_findings",
                label="No risk findings produced",
                detail=(
                    "The investigation completed without identifying a risk that the "
                    "evidence supports. This is a finding in itself and should be "
                    "reviewed rather than assumed correct."
                ),
                contribution=0.0,
                direction="neutral",
            )
        ],
        category_levels={},
        scored_findings=[],
        portfolio_strength=(
            EvidenceStrength.INSUFFICIENT if not coverage else EvidenceStrength.WEAK
        ),
    )


def categories_in_scope(findings: list[RiskFinding]) -> list[RiskCategory]:
    """Distinct categories represented in a finding set, in taxonomy order."""
    present = {f.category for f in findings}
    return [c for c in RiskCategory if c in present]

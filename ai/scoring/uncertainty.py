"""Interpretable uncertainty for individual findings.

ARGUS never shows a number like "97% confident". A language model's stated
confidence is not calibrated, and presenting it as a probability invites exactly
the automation bias this product is designed to resist.

Instead, evidence strength is computed here from signals a reviewer can inspect
and dispute:

==========================  ===============================================
Signal                      Why it belongs in the calculation
==========================  ===============================================
supporting evidence count   One quote is an anecdote; several is a pattern.
independent source count    Three quotes from one document are one source.
grounding quality           Did the quotes actually verify against the text?
verifier verdict            An adversarial second pass over the same claim.
contradicting evidence      Contested findings deserve less confidence.
blocking information gaps   A known unknown weakens what we can assert.
==========================  ===============================================

The function is pure and deterministic, which is what makes it unit-testable
and what lets the UI explain a band rather than merely display it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.schemas.enums import EvidenceStrength, SupportStatus
from ai.schemas.models import EvidenceItem, RiskFinding

# Diminishing returns: the second corroborating quote is worth far more than
# the fifth, so the count signal saturates rather than growing linearly.
_COUNT_CURVE: dict[int, float] = {0: 0.00, 1: 0.26, 2: 0.46, 3: 0.60, 4: 0.68}
_COUNT_CEILING = 0.72

_VERIFIER_ADJUSTMENT: dict[SupportStatus, float] = {
    SupportStatus.SUPPORTED: 0.15,
    SupportStatus.PARTIALLY_SUPPORTED: -0.06,
    SupportStatus.UNSUPPORTED: -0.40,
    SupportStatus.CONFLICTING: -0.22,
}

_BANDS: tuple[tuple[float, EvidenceStrength], ...] = (
    (0.72, EvidenceStrength.STRONG),
    (0.50, EvidenceStrength.MODERATE),
    (0.28, EvidenceStrength.WEAK),
)


@dataclass(frozen=True)
class StrengthSignal:
    """A single named contribution to the evidence-strength score."""

    key: str
    label: str
    value: float
    detail: str


@dataclass(frozen=True)
class StrengthResult:
    """Outcome of an evidence-strength assessment."""

    strength: EvidenceStrength
    score: float
    signals: list[StrengthSignal] = field(default_factory=list)
    rationale: str = ""


def _count_component(n: int) -> float:
    return _COUNT_CURVE.get(n, _COUNT_CEILING) if n < 4 else _COUNT_CEILING


def assess_evidence_strength(
    finding: RiskFinding,
    evidence_by_id: dict[str, EvidenceItem],
    *,
    verifier_status: SupportStatus | None = None,
    blocking_gap: bool = False,
) -> StrengthResult:
    """Grade how well the available evidence carries ``finding``.

    Args:
        finding: The risk hypothesis under assessment.
        evidence_by_id: Every *grounded* evidence item available to the case.
            Citations absent from this mapping are treated as unusable, which
            is how fabricated or ungrounded references lose their weight.
        verifier_status: Verdict from the Evidence Verifier, when it ran.
        blocking_gap: Whether the planner recorded an information gap that
            blocks this finding's category.

    Returns:
        The band, the underlying score, and every signal that produced it.
    """
    supporting = [
        evidence_by_id[eid] for eid in finding.supporting_evidence_ids if eid in evidence_by_id
    ]
    contradicting = [
        evidence_by_id[eid] for eid in finding.contradicting_evidence_ids if eid in evidence_by_id
    ]
    signals: list[StrengthSignal] = []

    # --- Hard floors -------------------------------------------------------
    # These are rules, not weights: no amount of other signal should rescue a
    # finding with nothing behind it, or one the verifier rejected outright.
    if not supporting:
        return StrengthResult(
            strength=EvidenceStrength.INSUFFICIENT,
            score=0.0,
            signals=[
                StrengthSignal(
                    key="no_usable_citations",
                    label="No usable citations",
                    value=0.0,
                    detail=(
                        "The finding cites no evidence that survived grounding "
                        "verification against the source documents."
                    ),
                )
            ],
            rationale=(
                "Insufficient evidence: no cited evidence could be traced back to a "
                "source document."
            ),
        )

    if verifier_status is SupportStatus.UNSUPPORTED:
        return StrengthResult(
            strength=EvidenceStrength.INSUFFICIENT,
            score=0.0,
            signals=[
                StrengthSignal(
                    key="verifier_unsupported",
                    label="Verifier rejected the claim",
                    value=-0.40,
                    detail="The Evidence Verifier found the citations do not support the claim.",
                )
            ],
            rationale="Insufficient evidence: the verifier judged the claim unsupported.",
        )

    # --- Weighted signals --------------------------------------------------
    score = _count_component(len(supporting))
    signals.append(
        StrengthSignal(
            key="supporting_count",
            label="Corroborating evidence",
            value=score,
            detail=f"{len(supporting)} evidence item(s) cited in support.",
        )
    )

    distinct_docs = {e.document_id for e in supporting}
    independence = min(len(distinct_docs) - 1, 2) * 0.10
    score += independence
    signals.append(
        StrengthSignal(
            key="source_independence",
            label="Independent sources",
            value=independence,
            detail=(
                f"Evidence drawn from {len(distinct_docs)} distinct document(s); "
                "corroboration across documents counts for more than repetition within one."
            ),
        )
    )

    mean_grounding = sum(e.grounding_score for e in supporting) / len(supporting)
    grounding = (mean_grounding - 0.5) * 0.20
    score += grounding
    signals.append(
        StrengthSignal(
            key="grounding_quality",
            label="Quote grounding quality",
            value=grounding,
            detail=f"Mean verbatim-match score of cited quotes: {mean_grounding:.2f}.",
        )
    )

    if verifier_status is not None:
        adjustment = _VERIFIER_ADJUSTMENT.get(verifier_status, 0.0)
        score += adjustment
        signals.append(
            StrengthSignal(
                key="verifier_status",
                label=f"Verifier: {verifier_status.label}",
                value=adjustment,
                detail="Independent check of whether the citations carry the claim.",
            )
        )

    if contradicting:
        penalty = -0.10 - 0.04 * min(len(contradicting) - 1, 3)
        score += penalty
        signals.append(
            StrengthSignal(
                key="contradiction",
                label="Contradicting evidence present",
                value=penalty,
                detail=f"{len(contradicting)} evidence item(s) point the other way.",
            )
        )

    if blocking_gap:
        score -= 0.10
        signals.append(
            StrengthSignal(
                key="information_gap",
                label="Blocking information gap",
                value=-0.10,
                detail="The plan flagged missing information that bears on this category.",
            )
        )

    score = max(0.0, min(1.0, score))
    strength = next(
        (band for threshold, band in _BANDS if score >= threshold),
        EvidenceStrength.INSUFFICIENT,
    )

    return StrengthResult(
        strength=strength,
        score=round(score, 3),
        signals=signals,
        rationale=_build_rationale(
            strength, supporting, distinct_docs, contradicting, verifier_status
        ),
    )


def _build_rationale(
    strength: EvidenceStrength,
    supporting: list[EvidenceItem],
    distinct_docs: set[str],
    contradicting: list[EvidenceItem],
    verifier_status: SupportStatus | None,
) -> str:
    """Compose the one-line explanation shown next to the band in the UI."""
    parts = [
        f"{len(supporting)} grounded citation(s) across {len(distinct_docs)} document(s)",
    ]
    if verifier_status is not None:
        parts.append(f"verifier returned {verifier_status.label.lower()}")
    if contradicting:
        parts.append(f"{len(contradicting)} contradicting item(s) on record")
    else:
        parts.append("no contradicting evidence found")
    return f"{strength.label}: " + "; ".join(parts) + "."

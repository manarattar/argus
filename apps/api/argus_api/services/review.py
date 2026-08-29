"""Human review, overrides and finalisation.

This module is where the product principle stops being a slogan. An
investigation ends at ``awaiting_human_review`` and there is no code path that
moves it further without a recorded decision by a named person. Approval is not
a formality the UI can skip.

Every change an analyst makes is stored alongside the AI's original
recommendation rather than replacing it. That is what makes the override rate
measurable, and the override rate is the honest read on whether the system is
useful: near zero suggests rubber-stamping, very high suggests the model is not
earning its place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.domain import get_domain
from ai.schemas.enums import (
    EvidenceStrength,
    InvestigationStatus,
    Likelihood,
    ReviewDecision,
    RiskLevel,
    Severity,
)
from ai.schemas.models import Challenge, ClaimVerification, CoverageItem, PolicyMatch, RiskFinding
from ai.scoring.coverage import evaluate_escalation
from ai.scoring.engine import compute_assessment_score
from argus_api.db.models import (
    Case,
    ChallengeRow,
    Investigation,
    Override,
    PolicyMatchRow,
    Review,
    Risk,
    VerificationRow,
)
from argus_api.services import audit


class ReviewError(RuntimeError):
    """Raised when a review action is not valid for the current state."""


@dataclass(frozen=True)
class RescoreResult:
    """Outcome of recomputing the rating after human edits."""

    overall_level: RiskLevel
    overall_score: float
    factors: list[dict[str, Any]]
    category_levels: dict[str, str]
    changed: bool


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


def override_severity(
    session: Session,
    *,
    investigation: Investigation,
    risk: Risk,
    new_severity: Severity,
    rationale: str,
    actor: str,
) -> Override:
    """Record an analyst changing a finding's severity.

    A rationale is mandatory. An override without a reason is not reviewable and
    would be worthless in an audit, so the requirement is enforced here rather
    than left to the form.
    """
    if not rationale.strip():
        raise ReviewError("A rationale is required when changing a severity.")
    if risk.severity == new_severity.value:
        raise ReviewError("The finding already has that severity.")

    previous = risk.severity
    risk.severity = new_severity.value

    record = Override(
        investigation_id=investigation.id,
        risk_id=risk.risk_id,
        field="severity",
        ai_value=risk.ai_severity,
        human_value=new_severity.value,
        rationale=rationale.strip(),
        actor=actor,
    )
    session.add(record)

    audit.record(
        session,
        case_id=investigation.case_id,
        investigation_id=investigation.id,
        actor=actor,
        action=audit.SEVERITY_OVERRIDDEN,
        summary=(
            f"Severity of '{risk.title}' changed from {previous} to " f"{new_severity.value}."
        ),
        entity_type="finding",
        entity_id=risk.risk_id,
        before={"severity": previous, "ai_severity": risk.ai_severity},
        after={"severity": new_severity.value, "rationale": rationale.strip()},
    )
    return record


def override_likelihood(
    session: Session,
    *,
    investigation: Investigation,
    risk: Risk,
    new_likelihood: Likelihood,
    rationale: str,
    actor: str,
) -> Override:
    """Record an analyst changing a finding's likelihood."""
    if not rationale.strip():
        raise ReviewError("A rationale is required when changing a likelihood.")
    if risk.likelihood == new_likelihood.value:
        raise ReviewError("The finding already has that likelihood.")

    previous = risk.likelihood
    risk.likelihood = new_likelihood.value

    record = Override(
        investigation_id=investigation.id,
        risk_id=risk.risk_id,
        field="likelihood",
        ai_value=risk.ai_likelihood,
        human_value=new_likelihood.value,
        rationale=rationale.strip(),
        actor=actor,
    )
    session.add(record)

    audit.record(
        session,
        case_id=investigation.case_id,
        investigation_id=investigation.id,
        actor=actor,
        action=audit.LIKELIHOOD_OVERRIDDEN,
        summary=(
            f"Likelihood of '{risk.title}' changed from {previous} to " f"{new_likelihood.value}."
        ),
        entity_type="finding",
        entity_id=risk.risk_id,
        before={"likelihood": previous},
        after={"likelihood": new_likelihood.value, "rationale": rationale.strip()},
    )
    return record


def mark_false_positive(
    session: Session,
    *,
    investigation: Investigation,
    risk: Risk,
    rationale: str,
    actor: str,
) -> Override:
    """Flag a finding as a false positive.

    The finding is not deleted. It stays visible, marked, and excluded from the
    rating - so the record still shows what the system proposed and why a human
    disagreed.
    """
    if not rationale.strip():
        raise ReviewError("A rationale is required when marking a false positive.")

    risk.is_false_positive = True
    record = Override(
        investigation_id=investigation.id,
        risk_id=risk.risk_id,
        field="false_positive",
        ai_value="finding",
        human_value="false_positive",
        rationale=rationale.strip(),
        actor=actor,
    )
    session.add(record)

    audit.record(
        session,
        case_id=investigation.case_id,
        investigation_id=investigation.id,
        actor=actor,
        action=audit.FALSE_POSITIVE_MARKED,
        summary=f"'{risk.title}' marked as a false positive.",
        entity_type="finding",
        entity_id=risk.risk_id,
        after={"rationale": rationale.strip()},
    )
    return record


def add_note(
    session: Session,
    *,
    investigation: Investigation,
    risk: Risk,
    note: str,
    actor: str,
) -> None:
    """Attach an analyst comment to a finding."""
    if not note.strip():
        raise ReviewError("The note is empty.")
    previous = risk.analyst_note
    risk.analyst_note = note.strip()
    audit.record(
        session,
        case_id=investigation.case_id,
        investigation_id=investigation.id,
        actor=actor,
        action=audit.NOTE_ADDED,
        summary=f"Analyst note added to '{risk.title}'.",
        entity_type="finding",
        entity_id=risk.risk_id,
        before={"note": previous},
        after={"note": risk.analyst_note},
    )


# ---------------------------------------------------------------------------
# Rescoring after human edits
# ---------------------------------------------------------------------------


def _to_finding(row: Risk) -> RiskFinding:
    """Rebuild the scoring input from a stored row, using effective values."""
    return RiskFinding(
        risk_id=row.risk_id,
        title=row.title,
        category=row.category,
        description=row.description,
        severity=Severity(row.severity),
        likelihood=Likelihood(row.likelihood),
        supporting_evidence_ids=list(row.supporting_evidence_ids),
        contradicting_evidence_ids=list(row.contradicting_evidence_ids),
        assumptions=list(row.assumptions),
        open_questions=list(row.open_questions),
        mitigating_factors=list(row.mitigating_factors),
        evidence_strength=EvidenceStrength(row.evidence_strength),
        strength_rationale=row.strength_rationale,
        inherent_score=row.inherent_score,
    )


def rescore(session: Session, investigation: Investigation) -> RescoreResult:
    """Recompute the rating from the current, human-adjusted findings.

    The same deterministic engine runs on the same shape of input, so an analyst
    can see exactly how their edit moved the number - and the explanation stays
    consistent with the one shown before they touched it.
    """
    previous_level = investigation.overall_level
    previous_score = investigation.overall_score

    rows = [r for r in investigation.risks if not r.is_false_positive]
    findings = [_to_finding(r) for r in rows]

    matches = [
        PolicyMatch(
            match_id=m.match_id,
            risk_id=m.risk_id,
            policy_id=m.policy_id,
            clause_reference=m.clause_reference,
            clause_title=m.clause_title,
            relevance=m.relevance,
            trigger_type=m.trigger_type,
            threshold_assessment=m.threshold_assessment,
            sufficiency_caveat=m.sufficiency_caveat,
        )
        for m in session.execute(
            select(PolicyMatchRow).where(PolicyMatchRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    ]
    challenges = [
        Challenge(
            challenge_id=c.challenge_id,
            risk_id=c.risk_id,
            challenge_type=c.challenge_type,
            argument=c.argument,
            counter_evidence_ids=list(c.counter_evidence_ids),
            suggested_revision=c.suggested_revision,
            proposed_severity=Severity(c.proposed_severity) if c.proposed_severity else None,
            unresolved=c.unresolved,
        )
        for c in session.execute(
            select(ChallengeRow).where(ChallengeRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    ]
    verifications = [
        ClaimVerification(
            verification_id=v.verification_id,
            risk_id=v.risk_id,
            claim=v.claim,
            status=v.status,
            reasoning=v.reasoning,
            citations_checked=list(v.citations_checked),
            irrelevant_citation_ids=list(v.irrelevant_citation_ids),
            downgrade_recommended=v.downgrade_recommended,
        )
        for v in session.execute(
            select(VerificationRow).where(VerificationRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    ]
    coverage = [
        CoverageItem(
            category=item["category"],
            status=item["status"],
            expected=item.get("expected", ""),
            found_evidence_ids=item.get("found_evidence_ids", []),
            note=item.get("note", ""),
        )
        for item in (investigation.coverage or [])
    ]

    score = compute_assessment_score(
        findings,
        policy_matches=matches,
        verifications=verifications,
        challenges=challenges,
        coverage=coverage,
    )

    investigation.overall_level = score.overall_level.value
    investigation.overall_score = score.overall_score
    investigation.evidence_strength = score.portfolio_strength.value
    investigation.score_factors = [f.model_dump() for f in score.factors]
    investigation.category_levels = {k: v.value for k, v in score.category_levels.items()}
    investigation.escalation_reasons = evaluate_escalation(
        get_domain(investigation.domain_key), findings, matches, score.overall_level
    )

    for row, scored in zip(rows, score.scored_findings, strict=True):
        row.adjusted_score = scored.adjusted

    return RescoreResult(
        overall_level=score.overall_level,
        overall_score=score.overall_score,
        factors=investigation.score_factors,
        category_levels=investigation.category_levels,
        changed=(
            previous_level != score.overall_level.value
            or abs(previous_score - score.overall_score) > 0.01
        ),
    )


# ---------------------------------------------------------------------------
# Finalisation
# ---------------------------------------------------------------------------

_TERMINAL_STATUS = {
    ReviewDecision.APPROVE: ("completed", "approved"),
    ReviewDecision.REJECT: ("completed", "rejected"),
    ReviewDecision.ESCALATE: ("awaiting_human_review", "escalated"),
    ReviewDecision.REQUEST_DEEPER_INVESTIGATION: (
        "awaiting_human_review",
        "investigating",
    ),
    ReviewDecision.MODIFY: ("awaiting_human_review", "in_review"),
}


def submit_review(
    session: Session,
    *,
    investigation: Investigation,
    case: Case,
    decision: ReviewDecision,
    comment: str,
    actor: str,
) -> Review:
    """Record the human decision that releases (or holds) an investigation.

    Approval is refused while a domain escalation rule is outstanding. The
    analyst can still escalate or reject; they cannot approve past a control.
    """
    if investigation.status == InvestigationStatus.FAILED.value:
        raise ReviewError("A failed investigation cannot be reviewed. Re-run it first.")

    if decision is ReviewDecision.APPROVE and investigation.escalation_reasons:
        raise ReviewError(
            "This assessment triggers a mandatory escalation and cannot be "
            "approved directly: " + "; ".join(investigation.escalation_reasons)
        )

    if decision in {ReviewDecision.REJECT, ReviewDecision.ESCALATE} and not comment.strip():
        raise ReviewError("A comment is required when rejecting or escalating.")

    ai_level = _original_ai_level(investigation)
    investigation_status, case_status = _TERMINAL_STATUS[decision]

    review = Review(
        investigation_id=investigation.id,
        decision=decision.value,
        comment=comment.strip(),
        actor=actor,
        ai_overall_level=ai_level,
        final_overall_level=investigation.overall_level,
    )
    session.add(review)

    investigation.status = investigation_status
    if decision is ReviewDecision.APPROVE:
        investigation.completed_at = datetime.now(UTC)
    case.status = case_status

    audit.record(
        session,
        case_id=case.id,
        investigation_id=investigation.id,
        actor=actor,
        action=audit.REVIEW_SUBMITTED,
        summary=(
            f"Analyst decision: {decision.label}. Final rating "
            f"{investigation.overall_level or 'none'} "
            f"(AI proposed {ai_level or 'none'})."
        ),
        entity_type="investigation",
        entity_id=investigation.id,
        before={"ai_overall_level": ai_level},
        after={
            "decision": decision.value,
            "final_overall_level": investigation.overall_level,
            "comment": comment.strip(),
        },
    )
    return review


def _original_ai_level(investigation: Investigation) -> str:
    """The rating the system proposed before any human edit.

    Recomputed from the stored ``ai_severity``/``ai_likelihood`` columns rather
    than cached, so it stays correct however many edits were made.
    """
    findings: list[RiskFinding] = []
    for row in investigation.risks:
        finding = _to_finding(row)
        findings.append(
            finding.model_copy(
                update={
                    "severity": Severity(row.ai_severity),
                    "likelihood": Likelihood(row.ai_likelihood),
                }
            )
        )
    if not findings:
        return investigation.overall_level
    coverage = [
        CoverageItem(
            category=item["category"],
            status=item["status"],
            expected=item.get("expected", ""),
            found_evidence_ids=item.get("found_evidence_ids", []),
            note=item.get("note", ""),
        )
        for item in (investigation.coverage or [])
    ]
    return compute_assessment_score(findings, coverage=coverage).overall_level.value


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def override_metrics(session: Session) -> dict[str, Any]:
    """Aggregate human-vs-AI divergence for the operations dashboard."""
    total_findings = session.execute(select(func.count(Risk.id))).scalar_one() or 0
    overridden = (
        session.execute(select(func.count(func.distinct(Override.risk_id)))).scalar_one() or 0
    )
    # Written as a comprehension rather than dict() so the annotation survives:
    # SQLAlchemy Row tuples do not narrow to dict[str, int] on their own.
    by_field: dict[str, int] = {  # noqa: C416
        field: count
        for field, count in session.execute(
            select(Override.field, func.count(Override.id)).group_by(Override.field)
        ).all()
    }
    reviews = session.execute(select(Review)).scalars().all()
    level_changes = sum(
        1 for r in reviews if r.ai_overall_level and r.ai_overall_level != r.final_overall_level
    )

    return {
        "total_findings": total_findings,
        "findings_overridden": overridden,
        "override_rate": round(overridden / total_findings, 3) if total_findings else 0.0,
        "overrides_by_field": by_field,
        "reviews_submitted": len(reviews),
        "reviews_changing_overall_level": level_changes,
        "decisions": {
            decision: sum(1 for r in reviews if r.decision == decision)
            for decision in {r.decision for r in reviews}
        },
    }

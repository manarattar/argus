"""Row-to-payload conversion.

Kept in one module so the shape of every API response is defined in a single
place, and so the frontend's TypeScript types have one thing to track.

Two conventions run throughout, both in service of the product principle:

* Anything the AI proposed is sent alongside anything a human changed, never
  replaced by it (``ai_severity`` beside ``severity``).
* Anything uncertain is sent with the reason for the uncertainty attached
  (``evidence_strength`` beside ``strength_rationale``), so the UI never has to
  render a bare label it cannot explain.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.schemas.enums import EvidenceStrength, Likelihood, RiskCategory, RiskLevel, Severity
from argus_api.db.models import (
    Case,
    ChallengeRow,
    Document,
    Evidence,
    Investigation,
    InvestigationStep,
    Override,
    PolicyMatchRow,
    Review,
    Risk,
    VerificationRow,
)


def _label(value: str, enum_type: Any) -> str:
    """Human label for a stored enum value, tolerant of unexpected data."""
    try:
        return enum_type(value).label
    except (ValueError, KeyError):
        return value.replace("_", " ").title() if value else ""


def case_payload(case: Case, *, investigation: Investigation | None = None) -> dict[str, Any]:
    return {
        "id": case.id,
        "reference": case.reference,
        "organisation": case.organisation,
        "review_type": case.review_type,
        "domain_key": case.domain_key,
        "status": case.status,
        "analyst": case.analyst,
        "sector": case.sector,
        "jurisdiction": case.jurisdiction,
        "background": case.background,
        "created_at": case.created_at.isoformat(),
        "updated_at": case.updated_at.isoformat(),
        "document_count": len(case.documents),
        "latest_investigation": (investigation_summary(investigation) if investigation else None),
    }


def investigation_summary(investigation: Investigation) -> dict[str, Any]:
    return {
        "id": investigation.id,
        "case_id": investigation.case_id,
        "status": investigation.status,
        "overall_level": investigation.overall_level,
        "overall_level_label": _label(investigation.overall_level, RiskLevel),
        "overall_score": investigation.overall_score,
        "evidence_strength": investigation.evidence_strength,
        "evidence_strength_label": _label(investigation.evidence_strength, EvidenceStrength),
        "findings": len(investigation.risks),
        "evidence_count": len(investigation.evidence),
        "escalation_reasons": investigation.escalation_reasons or [],
        "demo_mode": investigation.demo_mode,
        "model_name": investigation.model_name,
        "duration_ms": investigation.duration_ms,
        "estimated_cost_usd": investigation.total_cost_usd,
        "started_at": investigation.started_at.isoformat(),
        "completed_at": (
            investigation.completed_at.isoformat() if investigation.completed_at else None
        ),
        "has_errors": bool(investigation.errors),
    }


def evidence_payload(row: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": row.evidence_id,
        "statement": row.statement,
        "quote": row.quote,
        "kind": row.kind,
        "category": row.category,
        "category_label": _label(row.category, RiskCategory),
        "document_id": row.document_id,
        "document_name": row.document_name,
        "section_reference": row.section_reference,
        "chunk_id": row.chunk_id,
        "materiality": row.materiality,
        "grounding_score": row.grounding_score,
        "is_grounded": row.is_grounded,
    }


def risk_payload(
    row: Risk,
    *,
    verification: VerificationRow | None = None,
    policy_matches: list[PolicyMatchRow] | None = None,
    challenges: list[ChallengeRow] | None = None,
    overrides: list[Override] | None = None,
) -> dict[str, Any]:
    return {
        "risk_id": row.risk_id,
        "title": row.title,
        "category": row.category,
        "category_label": _label(row.category, RiskCategory),
        "description": row.description,
        "severity": row.severity,
        "severity_label": _label(row.severity, Severity),
        "likelihood": row.likelihood,
        "likelihood_label": _label(row.likelihood, Likelihood),
        # The AI's original recommendation is always sent, so the UI can show
        # divergence without a second request.
        "ai_severity": row.ai_severity,
        "ai_likelihood": row.ai_likelihood,
        "was_overridden": (row.severity != row.ai_severity or row.likelihood != row.ai_likelihood),
        "supporting_evidence_ids": list(row.supporting_evidence_ids),
        "contradicting_evidence_ids": list(row.contradicting_evidence_ids),
        "assumptions": list(row.assumptions),
        "open_questions": list(row.open_questions),
        "mitigating_factors": list(row.mitigating_factors),
        "evidence_strength": row.evidence_strength,
        "evidence_strength_label": _label(row.evidence_strength, EvidenceStrength),
        "strength_rationale": row.strength_rationale,
        "inherent_score": row.inherent_score,
        "adjusted_score": row.adjusted_score,
        "mind_changer_increase": row.mind_changer_increase,
        "mind_changer_decrease": row.mind_changer_decrease,
        "is_false_positive": row.is_false_positive,
        "analyst_note": row.analyst_note,
        "verification": verification_payload(verification) if verification else None,
        "policy_matches": [policy_payload(m) for m in (policy_matches or [])],
        "challenges": [challenge_payload(c) for c in (challenges or [])],
        "overrides": [override_payload(o) for o in (overrides or [])],
    }


def policy_payload(row: PolicyMatchRow) -> dict[str, Any]:
    return {
        "match_id": row.match_id,
        "risk_id": row.risk_id,
        "policy_id": row.policy_id,
        "clause_reference": row.clause_reference,
        "clause_title": row.clause_title,
        "relevance": row.relevance,
        "trigger_type": row.trigger_type,
        "threshold_assessment": row.threshold_assessment,
        "sufficiency_caveat": row.sufficiency_caveat,
    }


def challenge_payload(row: ChallengeRow) -> dict[str, Any]:
    return {
        "challenge_id": row.challenge_id,
        "risk_id": row.risk_id,
        "challenge_type": row.challenge_type,
        "challenge_type_label": row.challenge_type.replace("_", " ").title(),
        "argument": row.argument,
        "counter_evidence_ids": list(row.counter_evidence_ids),
        "suggested_revision": row.suggested_revision,
        "proposed_severity": row.proposed_severity,
        "unresolved": row.unresolved,
        "on_demand": row.on_demand,
        "created_at": row.created_at.isoformat(),
    }


def verification_payload(row: VerificationRow) -> dict[str, Any]:
    return {
        "verification_id": row.verification_id,
        "risk_id": row.risk_id,
        "claim": row.claim,
        "status": row.status,
        "status_label": row.status.replace("_", " ").title(),
        "reasoning": row.reasoning,
        "citations_checked": list(row.citations_checked),
        "irrelevant_citation_ids": list(row.irrelevant_citation_ids),
        "downgrade_recommended": row.downgrade_recommended,
    }


def override_payload(row: Override) -> dict[str, Any]:
    return {
        "id": row.id,
        "risk_id": row.risk_id,
        "field": row.field,
        "ai_value": row.ai_value,
        "human_value": row.human_value,
        "rationale": row.rationale,
        "actor": row.actor,
        "created_at": row.created_at.isoformat(),
    }


def step_payload(row: InvestigationStep) -> dict[str, Any]:
    return {
        "step_id": row.step_id,
        "ordinal": row.ordinal,
        "name": row.name,
        "capability": row.capability,
        "status": row.status,
        "summary": row.summary,
        "detail": row.detail,
        "prompt_reference": row.prompt_reference,
        "model": row.model,
        "attempts": row.attempts,
        "retries": row.retries,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "estimated_cost_usd": row.cost_usd,
        "duration_ms": row.duration_ms,
        "replayed": row.replayed,
        "error": row.error,
        "started_at": row.started_at.isoformat(),
    }


def document_payload(row: Document) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "doc_kind": row.doc_kind,
        "code": row.code,
        "description": row.description,
        "is_synthetic": row.is_synthetic,
        "characters": len(row.content),
        "chunks": len(row.chunks),
    }


def review_payload(row: Review) -> dict[str, Any]:
    return {
        "id": row.id,
        "decision": row.decision,
        "comment": row.comment,
        "actor": row.actor,
        "ai_overall_level": row.ai_overall_level,
        "final_overall_level": row.final_overall_level,
        "changed_overall_level": row.ai_overall_level != row.final_overall_level,
        "created_at": row.created_at.isoformat(),
    }


def investigation_detail(session: Session, investigation: Investigation) -> dict[str, Any]:
    """The full payload behind the case investigation screen."""
    verifications = {
        v.risk_id: v
        for v in session.execute(
            select(VerificationRow).where(VerificationRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    }
    policy_rows = (
        session.execute(
            select(PolicyMatchRow).where(PolicyMatchRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    challenge_rows = (
        session.execute(
            select(ChallengeRow).where(ChallengeRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    override_rows = (
        session.execute(select(Override).where(Override.investigation_id == investigation.id))
        .scalars()
        .all()
    )
    review_rows = (
        session.execute(
            select(Review)
            .where(Review.investigation_id == investigation.id)
            .order_by(Review.created_at.desc())
        )
        .scalars()
        .all()
    )

    by_risk_policy: dict[str, list[PolicyMatchRow]] = {}
    for match in policy_rows:
        by_risk_policy.setdefault(match.risk_id, []).append(match)
    by_risk_challenge: dict[str, list[ChallengeRow]] = {}
    for challenge in challenge_rows:
        by_risk_challenge.setdefault(challenge.risk_id, []).append(challenge)
    by_risk_override: dict[str, list[Override]] = {}
    for override in override_rows:
        by_risk_override.setdefault(override.risk_id, []).append(override)

    risks = sorted(investigation.risks, key=lambda r: r.adjusted_score, reverse=True)

    return {
        **investigation_summary(investigation),
        "domain_key": investigation.domain_key,
        "model_backend": investigation.model_backend,
        "embedding_model": investigation.embedding_model,
        "retrieval_quality": investigation.retrieval_quality,
        "score_factors": investigation.score_factors or [],
        "category_levels": investigation.category_levels or {},
        "coverage": investigation.coverage or [],
        "narrative": investigation.narrative or {},
        "integrity": investigation.integrity or {},
        "rejected_evidence": investigation.rejected_evidence or [],
        "errors": investigation.errors or [],
        "tokens": {
            "input": investigation.total_input_tokens,
            "output": investigation.total_output_tokens,
        },
        "risks": [
            risk_payload(
                r,
                verification=verifications.get(r.risk_id),
                policy_matches=by_risk_policy.get(r.risk_id, []),
                challenges=by_risk_challenge.get(r.risk_id, []),
                overrides=by_risk_override.get(r.risk_id, []),
            )
            for r in risks
        ],
        "evidence": [evidence_payload(e) for e in investigation.evidence],
        "policy_matches": [policy_payload(m) for m in policy_rows],
        "challenges": [challenge_payload(c) for c in challenge_rows],
        "verifications": [verification_payload(v) for v in verifications.values()],
        "overrides": [override_payload(o) for o in override_rows],
        "reviews": [review_payload(r) for r in review_rows],
        "steps": [step_payload(s) for s in sorted(investigation.steps, key=lambda s: s.ordinal)],
    }

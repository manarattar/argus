"""Human review endpoints: overrides, notes, targeted challenge, decisions.

Every route here writes an audit event and, where the rating can move,
recomputes it with the same deterministic engine the investigation used. The
analyst therefore sees the consequence of their edit immediately and explained,
rather than an opaque number that changed.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.providers.base import LLMError
from ai.providers.structured import SchemaValidationFailure
from ai.schemas.enums import Likelihood, ReviewDecision, Severity
from argus_api.db.models import Case, ChallengeRow, Investigation, Risk
from argus_api.db.session import get_db
from argus_api.serializers import (
    challenge_payload,
    investigation_detail,
    review_payload,
    risk_payload,
)
from argus_api.services import audit
from argus_api.services import review as review_service
from argus_api.services.qa import QuestionError, challenge_on_demand
from argus_api.services.runtime import get_llm_provider

router = APIRouter(prefix="/api/investigations", tags=["review"])

DbSession = Annotated[Session, Depends(get_db)]


class SeverityOverrideRequest(BaseModel):
    severity: Severity
    rationale: str = Field(min_length=10, max_length=1000)
    actor: str = Field(default="analyst", max_length=120)


class LikelihoodOverrideRequest(BaseModel):
    likelihood: Likelihood
    rationale: str = Field(min_length=10, max_length=1000)
    actor: str = Field(default="analyst", max_length=120)


class FalsePositiveRequest(BaseModel):
    rationale: str = Field(min_length=10, max_length=1000)
    actor: str = Field(default="analyst", max_length=120)


class NoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
    actor: str = Field(default="analyst", max_length=120)


class ReviewRequest(BaseModel):
    decision: ReviewDecision
    comment: str = Field(default="", max_length=2000)
    actor: str = Field(default="analyst", max_length=120)


def _load(session: Session, investigation_id: str) -> tuple[Investigation, Case]:
    investigation = session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    case = session.get(Case, investigation.case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found.")
    return investigation, case


def _load_risk(session: Session, investigation: Investigation, risk_id: str) -> Risk:
    risk = session.execute(
        select(Risk).where(Risk.investigation_id == investigation.id, Risk.risk_id == risk_id)
    ).scalar_one_or_none()
    if risk is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found.")
    return risk


def _rescored(session: Session, investigation: Investigation) -> dict[str, Any]:
    result = review_service.rescore(session, investigation)
    return {
        "overall_level": result.overall_level.value,
        "overall_score": result.overall_score,
        "factors": result.factors,
        "category_levels": result.category_levels,
        "changed": result.changed,
        "escalation_reasons": investigation.escalation_reasons or [],
    }


@router.patch("/{investigation_id}/findings/{risk_id}/severity")
def set_severity(
    investigation_id: str,
    risk_id: str,
    payload: SeverityOverrideRequest,
    session: DbSession,
) -> dict[str, Any]:
    investigation, _ = _load(session, investigation_id)
    risk = _load_risk(session, investigation, risk_id)
    try:
        review_service.override_severity(
            session,
            investigation=investigation,
            risk=risk,
            new_severity=payload.severity,
            rationale=payload.rationale,
            actor=payload.actor,
        )
    except review_service.ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    assessment = _rescored(session, investigation)
    session.commit()
    session.refresh(risk)
    return {"finding": risk_payload(risk), "assessment": assessment}


@router.patch("/{investigation_id}/findings/{risk_id}/likelihood")
def set_likelihood(
    investigation_id: str,
    risk_id: str,
    payload: LikelihoodOverrideRequest,
    session: DbSession,
) -> dict[str, Any]:
    investigation, _ = _load(session, investigation_id)
    risk = _load_risk(session, investigation, risk_id)
    try:
        review_service.override_likelihood(
            session,
            investigation=investigation,
            risk=risk,
            new_likelihood=payload.likelihood,
            rationale=payload.rationale,
            actor=payload.actor,
        )
    except review_service.ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    assessment = _rescored(session, investigation)
    session.commit()
    session.refresh(risk)
    return {"finding": risk_payload(risk), "assessment": assessment}


@router.post("/{investigation_id}/findings/{risk_id}/false-positive")
def mark_false_positive(
    investigation_id: str,
    risk_id: str,
    payload: FalsePositiveRequest,
    session: DbSession,
) -> dict[str, Any]:
    investigation, _ = _load(session, investigation_id)
    risk = _load_risk(session, investigation, risk_id)
    try:
        review_service.mark_false_positive(
            session,
            investigation=investigation,
            risk=risk,
            rationale=payload.rationale,
            actor=payload.actor,
        )
    except review_service.ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    assessment = _rescored(session, investigation)
    session.commit()
    session.refresh(risk)
    return {"finding": risk_payload(risk), "assessment": assessment}


@router.post("/{investigation_id}/findings/{risk_id}/note")
def add_note(
    investigation_id: str, risk_id: str, payload: NoteRequest, session: DbSession
) -> dict[str, Any]:
    investigation, _ = _load(session, investigation_id)
    risk = _load_risk(session, investigation, risk_id)
    try:
        review_service.add_note(
            session,
            investigation=investigation,
            risk=risk,
            note=payload.note,
            actor=payload.actor,
        )
    except review_service.ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    session.commit()
    session.refresh(risk)
    return {"finding": risk_payload(risk)}


@router.post("/{investigation_id}/findings/{risk_id}/challenge")
def request_challenge(investigation_id: str, risk_id: str, session: DbSession) -> dict[str, Any]:
    """Ask the Challenger for the strongest case against one finding."""
    investigation, case = _load(session, investigation_id)
    risk = _load_risk(session, investigation, risk_id)

    try:
        challenges, result = challenge_on_demand(
            session, investigation, risk=risk, provider=get_llm_provider()
        )
    except QuestionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except (LLMError, SchemaValidationFailure) as exc:
        # Surface the real reason rather than an empty result. In Demo Mode this
        # is how the UI learns there is no recording for this prompt.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"The Challenger could not run: {exc}",
        ) from exc

    stored: list[ChallengeRow] = []
    for index, challenge in enumerate(challenges):
        row_id = f"{investigation.id}:od:{risk.risk_id}:{index}:{challenge.challenge_id}"
        row = session.get(ChallengeRow, row_id)
        if row is None:
            row = ChallengeRow(id=row_id, investigation_id=investigation.id)
            session.add(row)
        row.challenge_id = challenge.challenge_id
        row.risk_id = risk.risk_id
        row.challenge_type = challenge.challenge_type
        row.argument = challenge.argument
        row.counter_evidence_ids = list(challenge.counter_evidence_ids)
        row.suggested_revision = challenge.suggested_revision
        row.proposed_severity = (
            challenge.proposed_severity.value if challenge.proposed_severity else ""
        )
        row.unresolved = challenge.unresolved
        row.on_demand = True
        stored.append(row)

    audit.record(
        session,
        case_id=case.id,
        investigation_id=investigation.id,
        actor="analyst",
        actor_type="ai",
        action=audit.CHALLENGE_REQUESTED,
        summary=(
            f"Targeted challenge requested against '{risk.title}'; "
            f"{len(stored)} argument(s) returned."
        ),
        entity_type="finding",
        entity_id=risk.risk_id,
    )
    session.commit()

    return {
        "challenges": [challenge_payload(r) for r in stored],
        "model": result.model,
        "replayed": result.replayed,
        "estimated_cost_usd": result.total_cost_usd,
    }


@router.post("/{investigation_id}/review")
def submit_review(
    investigation_id: str, payload: ReviewRequest, session: DbSession
) -> dict[str, Any]:
    """Record the human decision. The only route that can complete a case."""
    investigation, case = _load(session, investigation_id)
    try:
        review = review_service.submit_review(
            session,
            investigation=investigation,
            case=case,
            decision=payload.decision,
            comment=payload.comment,
            actor=payload.actor,
        )
    except review_service.ReviewError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    session.commit()
    session.refresh(investigation)
    return {
        "review": review_payload(review),
        "investigation": investigation_detail(session, investigation),
    }

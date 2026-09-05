"""Evidence graph, Scenario Lab and Ask ARGUS endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai.providers.base import LLMError
from ai.providers.structured import SchemaValidationFailure
from argus_api.core.limits import enforce_inference_limit
from argus_api.db.models import Investigation
from argus_api.db.session import get_db
from argus_api.services import audit
from argus_api.services.graph_view import build_evidence_graph, lineage_for_risk
from argus_api.services.qa import QuestionError, answer_question, serialise_answer
from argus_api.services.runtime import get_llm_provider
from argus_api.services.scenario import (
    SCENARIO_VARIABLES,
    VARIABLES_BY_KEY,
    observed_values,
    run_scenario,
)

router = APIRouter(prefix="/api/investigations", tags=["insights"])

DbSession = Annotated[Session, Depends(get_db)]


class QuestionRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    actor: str = Field(default="analyst", max_length=120)


class ScenarioRequest(BaseModel):
    variable: str = Field(max_length=64)
    value: float


def _load(session: Session, investigation_id: str) -> Investigation:
    investigation = session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return investigation


@router.get("/{investigation_id}/graph")
def get_graph(investigation_id: str, session: DbSession) -> dict[str, Any]:
    """Nodes and edges for the evidence graph."""
    investigation = _load(session, investigation_id)
    graph = build_evidence_graph(session, investigation)
    return graph.to_dict()


@router.get("/{investigation_id}/graph/lineage/{risk_id}")
def get_lineage(investigation_id: str, risk_id: str, session: DbSession) -> dict[str, Any]:
    """Node ids in one finding's lineage, for click-to-highlight."""
    investigation = _load(session, investigation_id)
    graph = build_evidence_graph(session, investigation)
    lineage = lineage_for_risk(graph, risk_id)
    if not lineage["risk"]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Finding not found in graph.")
    return lineage


@router.get("/{investigation_id}/scenario/variables")
def get_scenario_variables(investigation_id: str, session: DbSession) -> dict[str, Any]:
    """The structured variables a scenario may vary, with observed values."""
    investigation = _load(session, investigation_id)
    return {
        "variables": [
            {
                "key": state.key,
                "label": state.label,
                "unit": state.unit,
                "description": state.description,
                "policy_reference": state.policy_reference,
                "current_value": state.current_value,
                "minimum": state.minimum,
                "maximum": state.maximum,
                "step": state.step,
                "source": state.source,
                "affects": state.affects,
            }
            for state in observed_values(session, investigation)
        ],
        "note": (
            "Scenarios adjust declared structured variables and recompute the "
            "rating with the same deterministic scoring rules. They do not "
            "introduce evidence and are not findings about the counterparty."
        ),
    }


@router.post("/{investigation_id}/scenario")
def post_scenario(
    investigation_id: str, payload: ScenarioRequest, session: DbSession
) -> dict[str, Any]:
    """Recompute the rating with one variable changed."""
    investigation = _load(session, investigation_id)
    if payload.variable not in VARIABLES_BY_KEY:
        known = ", ".join(v.key for v in SCENARIO_VARIABLES)
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Unknown scenario variable. Available: {known}.",
        )
    try:
        result = run_scenario(
            session,
            investigation,
            variable_key=payload.variable,
            scenario_value=payload.value,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    audit.record(
        session,
        case_id=investigation.case_id,
        investigation_id=investigation.id,
        actor="analyst",
        action=audit.SCENARIO_RUN,
        summary=(
            f"Scenario run: {payload.variable} set to {payload.value:g}; "
            f"projected rating {result.scenario_level}."
        ),
        entity_type="scenario",
        entity_id=payload.variable,
    )
    session.commit()
    return result.to_dict()


@router.post("/{investigation_id}/ask", dependencies=[Depends(enforce_inference_limit)])
def ask(investigation_id: str, payload: QuestionRequest, session: DbSession) -> dict[str, Any]:
    """Answer an analyst question from the case record."""
    investigation = _load(session, investigation_id)
    try:
        outcome = answer_question(
            session,
            investigation,
            question=payload.question,
            provider=get_llm_provider(),
        )
    except QuestionError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except (LLMError, SchemaValidationFailure) as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Ask ARGUS could not answer: {exc}",
        ) from exc

    audit.record(
        session,
        case_id=investigation.case_id,
        investigation_id=investigation.id,
        actor=payload.actor,
        action=audit.QUESTION_ASKED,
        summary=f"Question asked: {payload.question[:160]}",
        entity_type="investigation",
        entity_id=investigation.id,
    )
    session.commit()

    return {
        **serialise_answer(outcome.answer),
        "model": outcome.result.model,
        "replayed": outcome.result.replayed,
        "estimated_cost_usd": outcome.result.total_cost_usd,
        "latency_ms": outcome.result.total_latency_ms,
    }


@router.get("/{investigation_id}/suggested-questions")
def suggested_questions(investigation_id: str, session: DbSession) -> dict[str, Any]:
    """Starter questions derived from this investigation's actual content.

    Generated from stored findings rather than hardcoded, so they always refer
    to something the case really contains.
    """
    investigation = _load(session, investigation_id)
    findings = sorted(
        [r for r in investigation.risks if not r.is_false_positive],
        key=lambda r: r.adjusted_score,
        reverse=True,
    )
    questions: list[str] = []

    if investigation.overall_level:
        questions.append(f"Why is the overall assessment {investigation.overall_level.title()}?")
    if findings:
        top = findings[0]
        questions.append(f"What evidence supports '{top.title}'?")
        questions.append(f"What evidence contradicts '{top.title}'?")
    weakest = [r for r in findings if r.evidence_strength in {"weak", "insufficient"}]
    if weakest:
        questions.append("Which conclusions rest on the weakest evidence?")
    if investigation.coverage:
        missing = [c for c in investigation.coverage if c["status"] != "complete"]
        if missing:
            questions.append("What information is still missing from this file?")
    questions.append("Which policy clauses are relevant to this assessment?")

    return {"questions": questions[:6]}

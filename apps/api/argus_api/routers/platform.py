"""Dashboard, operations, value case, architecture and runtime endpoints."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai.prompts.library import LIBRARY_VERSION, PROMPTS
from argus_api.db.session import get_db
from argus_api.services import analytics, audit, value_case
from argus_api.services.runtime import runtime_status

router = APIRouter(prefix="/api", tags=["platform"])

DbSession = Annotated[Session, Depends(get_db)]


class ValueCaseRequest(BaseModel):
    cases_per_month: float = Field(default=120.0, gt=0, le=100_000)
    manual_hours_per_case: float = Field(default=6.5, gt=0, le=200)
    assisted_hours_per_case: float = Field(default=3.4, ge=0, le=200)
    analyst_cost_per_hour: float = Field(default=85.0, ge=0, le=2000)
    ai_cost_per_case: float = Field(default=0.42, ge=0, le=1000)
    implementation_cost: float = Field(default=180_000.0, ge=0, le=100_000_000)
    annual_run_cost: float = Field(default=60_000.0, ge=0, le=100_000_000)
    adoption_rate: float = Field(default=0.7, ge=0, le=1)
    review_hours_per_case: float = Field(default=1.2, ge=0, le=200)
    sensitivity_variable: str = Field(default="assisted_hours_per_case", max_length=64)


@router.get("/runtime")
def get_runtime() -> dict[str, Any]:
    """What is actually running: live model or recordings, and which retriever."""
    return runtime_status()


@router.get("/dashboard")
def get_dashboard(session: DbSession) -> dict[str, Any]:
    """Executive dashboard metrics, computed from stored rows only."""
    return {**analytics.dashboard_summary(session), "runtime": runtime_status()}


@router.get("/operations")
def get_operations(session: DbSession) -> dict[str, Any]:
    """AI Operations metrics and the safe execution trace."""
    return {
        **analytics.operations_metrics(session),
        "runtime": runtime_status(),
        "trace_policy": (
            "Traces record what each step did - capability, tool, retrieval "
            "counts, duration, tokens and cost. They deliberately exclude model "
            "chain-of-thought, which is neither stored nor displayed."
        ),
    }


@router.get("/audit")
def get_global_audit(session: DbSession, limit: int = 100) -> dict[str, Any]:
    """Recent audit events across every case."""
    events = audit.history(session, limit=min(limit, 500))
    return {"events": [audit.serialise(e) for e in events]}


@router.post("/value-case")
def post_value_case(payload: ValueCaseRequest) -> dict[str, Any]:
    """Run the illustrative business-case model over supplied assumptions."""
    data = payload.model_dump()
    variable = data.pop("sensitivity_variable")
    assumptions = value_case.ValueAssumptions(**data)
    try:
        result = value_case.compute(assumptions)
        analysis = value_case.sensitivity(assumptions, variable=variable)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return {
        "result": result.to_dict(),
        "sensitivity": analysis,
        "notes": value_case.DEFAULT_NOTES,
    }


@router.get("/value-case/defaults")
def get_value_case_defaults() -> dict[str, Any]:
    """Default assumptions plus the note explaining each one."""
    assumptions = value_case.ValueAssumptions()
    return {
        "assumptions": asdict(assumptions),
        "notes": value_case.DEFAULT_NOTES,
        "disclaimer": value_case.DISCLAIMER,
    }


@router.get("/architecture")
def get_architecture(session: DbSession) -> dict[str, Any]:
    """Everything the in-app Architecture page renders.

    Served from the running system rather than written as static copy, so the
    page cannot drift out of step with the code: capabilities, domains and
    prompt versions are all read from the modules that define them.
    """
    return {
        "runtime": runtime_status(),
        "layers": [
            {
                "key": "client",
                "name": "Next.js workspace",
                "detail": (
                    "Analyst-facing application: case investigation, evidence "
                    "graph, review actions, evaluation and operations views."
                ),
            },
            {
                "key": "api",
                "name": "FastAPI service",
                "detail": (
                    "Typed HTTP boundary, request validation, serialisation and "
                    "the audit trail. Holds no model logic."
                ),
            },
            {
                "key": "orchestration",
                "name": "LangGraph investigation graph",
                "detail": (
                    "Stateful workflow over the agents, with conditional "
                    "routing, per-step failure handling and a mandatory human "
                    "review gate at the end."
                ),
            },
            {
                "key": "capabilities",
                "name": "Reusable AI capabilities",
                "detail": (
                    "Planning, evidence extraction, risk analysis, policy "
                    "retrieval, challenge, verification, synthesis and Q&A. "
                    "Domain-agnostic."
                ),
            },
            {
                "key": "controls",
                "name": "Deterministic controls",
                "detail": (
                    "Grounding verification, cross-reference integrity, the "
                    "uncertainty model and the scoring engine. No model call "
                    "happens in this layer."
                ),
            },
            {
                "key": "retrieval",
                "name": "Retrieval and storage",
                "detail": (
                    "Structure-aware chunking, embeddings and hybrid BM25 plus "
                    "vector search over SQLite or Postgres with pgvector."
                ),
            },
            {
                "key": "observability",
                "name": "Observability and evaluation",
                "detail": (
                    "Step traces, token and cost accounting, override metrics "
                    "and a reproducible evaluation harness."
                ),
            },
        ],
        "capabilities": [
            {
                "key": "planning",
                "name": "Intake & Planning",
                "reusable": True,
                "prompt": "intake_planner",
            },
            {
                "key": "evidence_extraction",
                "name": "Evidence Extraction",
                "reusable": True,
                "prompt": "evidence_extractor",
            },
            {
                "key": "risk_analysis",
                "name": "Risk Specialist",
                "reusable": True,
                "prompt": "risk_specialist",
            },
            {
                "key": "policy_retrieval",
                "name": "Policy Analyst",
                "reusable": True,
                "prompt": "policy_analyst",
            },
            {
                "key": "challenge",
                "name": "Challenger",
                "reusable": True,
                "prompt": "challenger",
            },
            {
                "key": "verification",
                "name": "Evidence Verifier",
                "reusable": True,
                "prompt": "evidence_verifier",
            },
            {
                "key": "synthesis",
                "name": "Risk Synthesis",
                "reusable": True,
                "prompt": "risk_synthesis",
            },
            {
                "key": "scoring",
                "name": "Scoring & Integrity",
                "reusable": True,
                "prompt": "",
            },
        ],
        "domains": analytics.domain_catalogue(),
        "prompts": {
            "library_version": LIBRARY_VERSION,
            "prompts": [
                {"id": p.id, "version": p.version, "reference": p.reference}
                for p in PROMPTS.values()
            ],
        },
        "controls": [
            {
                "name": "Quote grounding",
                "kind": "deterministic",
                "detail": (
                    "Every extracted quote is re-matched against the stored "
                    "source chunk. Unlocatable quotes are discarded before any "
                    "downstream agent sees them."
                ),
            },
            {
                "name": "Cross-reference integrity",
                "kind": "deterministic",
                "detail": (
                    "Findings, challenges and verifications may only cite "
                    "evidence that survived grounding. Unknown ids are stripped "
                    "and recorded."
                ),
            },
            {
                "name": "Schema validation",
                "kind": "deterministic",
                "detail": (
                    "Agent output is validated against a Pydantic model, with "
                    "the validation error fed back on retry. A step that never "
                    "validates fails visibly."
                ),
            },
            {
                "name": "Deterministic scoring",
                "kind": "deterministic",
                "detail": (
                    "The overall rating is computed from findings, policy "
                    "triggers, verification outcomes and coverage - never "
                    "generated as text."
                ),
            },
            {
                "name": "Prompt-injection boundary",
                "kind": "mitigation",
                "detail": (
                    "Document content is delimited and labelled as untrusted "
                    "data in every prompt. Backed by evaluation cases, because "
                    "prompt-level defence alone is not sufficient."
                ),
            },
            {
                "name": "Mandatory human review",
                "kind": "control",
                "detail": (
                    "The graph terminates at review. No code path completes an "
                    "assessment without a recorded human decision."
                ),
            },
        ],
        "operations": analytics.operations_metrics(session)["totals"],
    }

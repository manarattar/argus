"""Evaluation Lab endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai.evaluators.harness import load_cases
from argus_api.core.limits import enforce_inference_limit
from argus_api.core.settings import get_settings
from argus_api.db.models import EvalRun
from argus_api.db.session import get_db
from argus_api.services import evaluation
from argus_api.services.runtime import get_embedder, get_llm_provider

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])

DbSession = Annotated[Session, Depends(get_db)]


class RunRequest(BaseModel):
    suite: str | None = Field(default=None, max_length=64)
    case_id: str | None = Field(default=None, max_length=64)


@router.get("/cases")
def list_cases() -> dict[str, Any]:
    """The suite definition, so the Lab can show what is tested before a run."""
    settings = get_settings()
    try:
        cases = load_cases(settings.eval_data_dir / "cases.jsonl")
    except FileNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    by_category: dict[str, int] = {}
    for case in cases:
        by_category[case.category] = by_category.get(case.category, 0) + 1

    return {
        "total": len(cases),
        "requires_model": sum(1 for c in cases if c.requires_model),
        "deterministic": sum(1 for c in cases if not c.requires_model),
        "by_category": by_category,
        "cases": [
            {
                "id": c.id,
                "category": c.category,
                "description": c.description,
                "requires_model": c.requires_model,
                "tags": c.tags,
            }
            for c in cases
        ],
    }


@router.get("/latest")
def get_latest(session: DbSession) -> dict[str, Any]:
    """The most recent run, or an explicit empty state."""
    run = evaluation.latest_run(session)
    if run is None:
        return {
            "run": None,
            "history": [],
            "message": (
                "No evaluation has been run yet. Run one from this page, or with "
                "`make eval` from the repository root."
            ),
        }
    return {
        "run": evaluation.serialise_run(session, run),
        "history": evaluation.run_history(session),
    }


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: DbSession) -> dict[str, Any]:
    run = session.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluation run not found.")
    return {"run": evaluation.serialise_run(session, run)}


@router.post(
    "/run",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(enforce_inference_limit)],
)
def post_run(payload: RunRequest, session: DbSession) -> dict[str, Any]:
    """Execute the suite and persist the result.

    Deterministic cases always run. Model-dependent cases run only when a
    backend or recordings are available, and are otherwise reported as skipped.
    """
    settings = get_settings()
    try:
        report, run = evaluation.run_evaluation(
            session,
            dataset=settings.eval_data_dir / "cases.jsonl",
            provider=get_llm_provider(),
            embedder=get_embedder(),
            recordings_dir=settings.recordings_dir,
            suite=payload.suite,
            case_id=payload.case_id,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    session.commit()
    if run is None:  # pragma: no cover - persist is True on this path
        return {"metrics": report.metrics()}
    session.refresh(run)
    return {
        "run": evaluation.serialise_run(session, run),
        "history": evaluation.run_history(session),
    }

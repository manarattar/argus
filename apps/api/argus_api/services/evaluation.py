"""Running the evaluation suite and persisting the results.

Results are stored so the Evaluation Lab shows measurements from a real run
rather than numbers written into the page. Each run records the model backend,
the model, the embedding provider and whether responses were replayed, because
a pass rate is only meaningful next to the configuration that produced it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.evaluators.checks import HANDLERS
from ai.evaluators.harness import EvalContext, EvalReport, load_cases, run_suite
from ai.providers.base import LLMProvider
from ai.retrieval.embeddings import EmbeddingProvider
from argus_api.db.models import Case, EvalResult, EvalRun, Investigation
from argus_api.services import audit
from argus_api.services.corpus import build_index
from argus_api.services.investigation import latest_investigation


def _model_available(provider: LLMProvider, recordings_dir: Path) -> bool:
    """Can model-dependent cases actually execute?

    A replay backend counts only when recordings exist; otherwise those cases
    are skipped and reported as skipped, never as passes.
    """
    if provider.live:
        return True
    return recordings_dir.exists() and any(recordings_dir.glob("*.json"))


def run_evaluation(
    session: Session,
    *,
    dataset: Path,
    provider: LLMProvider,
    embedder: EmbeddingProvider,
    recordings_dir: Path,
    suite: str | None = None,
    case_id: str | None = None,
    persist: bool = True,
) -> tuple[EvalReport, EvalRun | None]:
    """Execute the suite and, by default, persist the run.

    Args:
        session: Open database session.
        dataset: Path to the JSONL case file.
        provider: Model backend for model-dependent cases.
        embedder: Embedding backend used to build the retrieval index.
        recordings_dir: Where replay fixtures live.
        suite: Optional suite filter.
        case_id: Optional case filter, for debugging a single check.
        persist: Whether to write the run to the database.

    Returns:
        The report and, when persisted, the stored run.
    """
    cases = load_cases(dataset, suite=suite)
    if case_id:
        cases = [c for c in cases if c.id == case_id]
        if not cases:
            raise ValueError(f"No evaluation case with id {case_id!r}")

    demo_case = session.execute(select(Case).limit(1)).scalar_one_or_none()
    investigation: Investigation | None = None
    index = None
    chunk_texts: dict[str, str] = {}

    if demo_case is not None:
        index = build_index(session, embedder, case_id=demo_case.id)
        chunk_texts = {c.chunk_id: c.text for c in index.chunks}
        investigation = latest_investigation(session, demo_case.id)

    model_available = _model_available(provider, recordings_dir)
    context = EvalContext(
        index=index,
        provider=provider,
        session=session,
        investigation=investigation,
        chunk_texts=chunk_texts,
        model_available=model_available,
        metadata={
            "model_backend": provider.name,
            "model_name": provider.model,
            "embedding_model": embedder.name,
            "embedding_semantic": embedder.semantic,
            "demo_mode": not provider.live,
            "model_available": model_available,
            "corpus_chunks": len(chunk_texts),
            "has_investigation": investigation is not None,
        },
    )

    report = run_suite(cases, HANDLERS, context)

    if not persist:
        return report, None

    metrics = report.metrics()
    run = EvalRun(
        suite=suite or "default",
        model_backend=provider.name,
        model_name=provider.model,
        embedding_model=embedder.name,
        demo_mode=not provider.live,
        total_cases=len(report.results),
        passed=report.passed,
        failed=report.failed,
        errored=report.errored + report.skipped,
        metrics=metrics,
        duration_ms=report.duration_ms,
        total_cost_usd=0.0,
    )
    session.add(run)
    session.flush()

    for result in report.results:
        payload = result.to_dict()
        session.add(
            EvalResult(
                run_id=run.id,
                case_id=payload["case_id"],
                suite=payload["suite"],
                category=payload["category"],
                description=payload["description"],
                passed=payload["passed"],
                score=payload["score"],
                expected=payload["expected"],
                actual=payload["actual"],
                detail=payload["detail"],
                error=payload["error"] or ("skipped" if result.outcome.skipped else ""),
                duration_ms=payload["duration_ms"],
            )
        )

    if demo_case is not None:
        audit.record(
            session,
            case_id=demo_case.id,
            actor="evaluation",
            actor_type="system",
            action=audit.EVALUATION_RUN,
            summary=(
                f"Evaluation suite executed: {report.passed} passed, "
                f"{report.failed} failed, {report.skipped} skipped."
            ),
            entity_type="eval_run",
            entity_id=run.id,
            after=metrics,
        )

    return report, run


def latest_run(session: Session) -> EvalRun | None:
    return session.execute(
        select(EvalRun).order_by(EvalRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()


def serialise_run(session: Session, run: EvalRun) -> dict[str, Any]:
    """Full payload for the Evaluation Lab."""
    results = session.execute(select(EvalResult).where(EvalResult.run_id == run.id)).scalars().all()
    return {
        "id": run.id,
        "suite": run.suite,
        "created_at": run.created_at.isoformat(),
        "model_backend": run.model_backend,
        "model_name": run.model_name,
        "embedding_model": run.embedding_model,
        "demo_mode": run.demo_mode,
        "total_cases": run.total_cases,
        "passed": run.passed,
        "failed": run.failed,
        "skipped_or_errored": run.errored,
        "duration_ms": run.duration_ms,
        "metrics": run.metrics,
        "results": [
            {
                "case_id": r.case_id,
                "category": r.category,
                "description": r.description,
                "passed": r.passed,
                "score": r.score,
                "expected": r.expected,
                "actual": r.actual,
                "detail": r.detail,
                "error": r.error,
                "duration_ms": r.duration_ms,
                "status": (
                    "skipped"
                    if r.error == "skipped"
                    else ("error" if r.error else ("passed" if r.passed else "failed"))
                ),
            }
            for r in sorted(results, key=lambda r: (r.category, r.case_id))
        ],
    }


def run_history(session: Session, *, limit: int = 20) -> list[dict[str, Any]]:
    runs = (
        session.execute(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit))
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat(),
            "model_name": r.model_name,
            "demo_mode": r.demo_mode,
            "passed": r.passed,
            "failed": r.failed,
            "total_cases": r.total_cases,
            "pass_rate": (r.metrics or {}).get("pass_rate"),
            "coverage": (r.metrics or {}).get("coverage"),
        }
        for r in runs
    ]

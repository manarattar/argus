"""Evaluation harness.

What this measures, and what it does not
----------------------------------------
The suite is split into two kinds of case, and the split is the point.

**Deterministic cases** exercise the controls: retrieval, quote grounding,
citation integrity, the scoring engine, escalation rules and the uncertainty
model. They need no model, so they produce real numbers on a fresh clone with no
account. These are the cases that verify the parts of ARGUS that are supposed to
be verifiable.

**Model cases** exercise the agents: schema conformance, citation discipline,
contradiction handling, refusal behaviour and resistance to prompt injection.
They need either a live model or a recording. When neither is available they are
reported as ``skipped`` - never as passed. A suite that scores 100% by not
running is worse than one that reports honest gaps.

Every run records the backend, the model, the embedding provider and whether it
was replayed, so two runs are only comparable when those match. Results are
persisted, so the Evaluation Lab shows measurements rather than assertions.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CaseHandler = Callable[["EvalCase", "EvalContext"], "CaseOutcome"]


@dataclass(frozen=True)
class EvalCase:
    """One test case, loaded from ``data/evals/cases.jsonl``."""

    id: str
    suite: str
    category: str
    description: str
    input: dict[str, Any]
    expected: dict[str, Any]
    requires_model: bool = False
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> EvalCase:
        return cls(
            id=raw["id"],
            suite=raw.get("suite", "default"),
            category=raw["category"],
            description=raw.get("description", ""),
            input=raw.get("input", {}),
            expected=raw.get("expected", {}),
            requires_model=raw.get("requires_model", False),
            tags=raw.get("tags", []),
        )


@dataclass
class CaseOutcome:
    """Result of running one case."""

    passed: bool
    score: float
    actual: str
    detail: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    error: str = ""


@dataclass
class EvalContext:
    """Everything the checks need, injected so they stay pure functions."""

    index: Any = None
    provider: Any = None
    session: Any = None
    investigation: Any = None
    chunk_texts: dict[str, str] = field(default_factory=dict)
    model_available: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CaseResult:
    """A case plus its outcome and timing."""

    case: EvalCase
    outcome: CaseOutcome
    duration_ms: int

    @property
    def status(self) -> str:
        if self.outcome.error:
            return "error"
        if self.outcome.skipped:
            return "skipped"
        return "passed" if self.outcome.passed else "failed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case.id,
            "suite": self.case.suite,
            "category": self.case.category,
            "description": self.case.description,
            "status": self.status,
            "passed": self.outcome.passed,
            "score": round(self.outcome.score, 4),
            "expected": json.dumps(self.case.expected, ensure_ascii=False),
            "actual": self.outcome.actual,
            "detail": self.outcome.detail,
            "error": self.outcome.error,
            "duration_ms": self.duration_ms,
            "requires_model": self.case.requires_model,
        }


@dataclass
class EvalReport:
    """Aggregate outcome of a suite run."""

    results: list[CaseResult]
    duration_ms: int
    context: dict[str, Any]

    @property
    def executed(self) -> list[CaseResult]:
        return [r for r in self.results if r.status in {"passed", "failed"}]

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "passed")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def errored(self) -> int:
        return sum(1 for r in self.results if r.status == "error")

    def metrics(self) -> dict[str, Any]:
        """Per-category and headline metrics.

        ``pass_rate`` is computed over *executed* cases only, and
        ``coverage`` reports what fraction of the suite actually ran - so a run
        with many skips cannot look like a strong result.
        """
        by_category: dict[str, dict[str, Any]] = {}
        for result in self.results:
            bucket = by_category.setdefault(
                result.case.category,
                {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "score_sum": 0.0},
            )
            bucket["total"] += 1
            if result.status == "passed":
                bucket["passed"] += 1
                bucket["score_sum"] += result.outcome.score
            elif result.status == "failed":
                bucket["failed"] += 1
                bucket["score_sum"] += result.outcome.score
            elif result.status == "skipped":
                bucket["skipped"] += 1

        for bucket in by_category.values():
            executed = bucket["passed"] + bucket["failed"]
            bucket["pass_rate"] = round(bucket["passed"] / executed, 3) if executed else None
            bucket["mean_score"] = round(bucket["score_sum"] / executed, 3) if executed else None
            bucket.pop("score_sum")

        executed = len(self.executed)
        return {
            "total_cases": len(self.results),
            "executed": executed,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "errored": self.errored,
            "pass_rate": round(self.passed / executed, 3) if executed else None,
            "coverage": round(executed / len(self.results), 3) if self.results else 0.0,
            "mean_score": (
                round(sum(r.outcome.score for r in self.executed) / executed, 3)
                if executed
                else None
            ),
            "by_category": by_category,
            "duration_ms": self.duration_ms,
            "context": self.context,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics(),
            "results": [r.to_dict() for r in self.results],
        }


def load_cases(path: Path, *, suite: str | None = None) -> list[EvalCase]:
    """Load cases from a JSONL file, optionally filtered to one suite."""
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found: {path}")

    cases: list[EvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        try:
            cases.append(EvalCase.from_json(json.loads(line)))
        except (json.JSONDecodeError, KeyError) as exc:
            raise ValueError(f"{path}:{line_number} is not a valid case: {exc}") from exc

    if suite:
        cases = [c for c in cases if c.suite == suite]
    return cases


def run_suite(
    cases: Iterable[EvalCase],
    handlers: Mapping[str, CaseHandler],
    context: EvalContext,
) -> EvalReport:
    """Execute every case with its category handler.

    A handler raising is recorded as an error for that case rather than
    aborting the run: one broken check should not hide the other thirty-nine
    results.
    """
    results: list[CaseResult] = []
    started = time.perf_counter()

    for case in cases:
        case_started = time.perf_counter()

        if case.requires_model and not context.model_available:
            results.append(
                CaseResult(
                    case=case,
                    outcome=CaseOutcome(
                        passed=False,
                        score=0.0,
                        actual="",
                        skipped=True,
                        detail={
                            "reason": (
                                "No model backend available. Configure a key, or "
                                "restore the demo recordings, to execute this case."
                            )
                        },
                    ),
                    duration_ms=0,
                )
            )
            continue

        handler = handlers.get(case.category)
        if handler is None:
            outcome = CaseOutcome(
                passed=False,
                score=0.0,
                actual="",
                error=f"No handler registered for category {case.category!r}",
            )
        else:
            try:
                outcome = handler(case, context)
            except Exception as exc:
                outcome = CaseOutcome(
                    passed=False,
                    score=0.0,
                    actual="",
                    error=f"{type(exc).__name__}: {exc}",
                )

        results.append(
            CaseResult(
                case=case,
                outcome=outcome,
                duration_ms=int((time.perf_counter() - case_started) * 1000),
            )
        )

    return EvalReport(
        results=results,
        duration_ms=int((time.perf_counter() - started) * 1000),
        context=context.metadata,
    )

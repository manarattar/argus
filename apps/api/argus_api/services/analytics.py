"""Aggregations for the Overview, AI Operations and Value Case pages.

Every figure returned here is computed from stored rows. Nothing is invented for
display: if no investigation has run, the dashboard reports zeros and says so,
because a demo dashboard showing plausible-looking numbers from nowhere is the
exact failure mode this project argues against.

Cost figures are labelled as estimates throughout, because they are derived from
a static price table rather than from billing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai.domain import list_domains
from ai.schemas.enums import CoverageStatus, RiskLevel
from ai.scoring.coverage import coverage_ratio
from argus_api.db.models import (
    Case,
    ChallengeRow,
    EvalRun,
    Evidence,
    Investigation,
    InvestigationStep,
    PolicyMatchRow,
    Risk,
    VerificationRow,
)
from argus_api.services.review import override_metrics


def _round(value: float | None, digits: int = 2) -> float:
    return round(value or 0.0, digits)


def dashboard_summary(session: Session) -> dict[str, Any]:
    """Headline metrics for the executive dashboard."""
    total_cases = session.execute(select(func.count(Case.id))).scalar_one() or 0
    active_cases = (
        session.execute(
            select(func.count(Case.id)).where(
                Case.status.in_(["draft", "investigating", "awaiting_review", "in_review"])
            )
        ).scalar_one()
        or 0
    )
    awaiting = (
        session.execute(
            select(func.count(Investigation.id)).where(
                Investigation.status == "awaiting_human_review"
            )
        ).scalar_one()
        or 0
    )
    investigations = session.execute(select(Investigation)).scalars().all()
    completed = [i for i in investigations if i.status != "failed"]

    avg_duration = sum(i.duration_ms for i in completed) / len(completed) if completed else 0.0
    total_cost = sum(i.total_cost_usd for i in investigations)
    replayed = [i for i in investigations if i.demo_mode]

    coverage_values = []
    for investigation in completed:
        items = investigation.coverage or []
        if items:
            complete = sum(1 for c in items if c["status"] == CoverageStatus.COMPLETE.value)
            coverage_values.append(complete / len(items))
    mean_coverage = sum(coverage_values) / len(coverage_values) if coverage_values else 0.0

    overrides = override_metrics(session)

    return {
        "cases": {
            "total": total_cases,
            "active": active_cases,
            "awaiting_review": awaiting,
        },
        "investigations": {
            "total": len(investigations),
            "completed": len(completed),
            "failed": len(investigations) - len(completed),
            "demo_mode": len(replayed),
        },
        "average_investigation_ms": int(avg_duration),
        "human_override_rate": overrides["override_rate"],
        "evidence_coverage": round(mean_coverage, 3),
        "estimated_cost_usd": _round(total_cost, 4),
        "cost_is_estimate": True,
        "risk_distribution": risk_distribution(session),
        "attention": cases_needing_attention(session),
        "recent": recent_investigations(session, limit=5),
        "system_health": system_health(session),
    }


def risk_distribution(session: Session) -> dict[str, int]:
    """Count of investigations by provisional rating."""
    rows = session.execute(
        select(Investigation.overall_level, func.count(Investigation.id))
        .where(Investigation.overall_level != "")
        .group_by(Investigation.overall_level)
    ).all()
    distribution = {level.value: 0 for level in RiskLevel}
    for level, count in rows:
        if level in distribution:
            distribution[level] = count
    return distribution


def category_distribution(session: Session) -> list[dict[str, Any]]:
    """Which risk categories findings actually land in."""
    rows = session.execute(
        select(Risk.category, func.count(Risk.id))
        .group_by(Risk.category)
        .order_by(func.count(Risk.id).desc())
    ).all()
    return [{"category": category, "count": count} for category, count in rows]


def cases_needing_attention(session: Session) -> list[dict[str, Any]]:
    """Cases held by a control or awaiting a human decision."""
    investigations = (
        session.execute(
            select(Investigation)
            .where(Investigation.status.in_(["awaiting_human_review", "failed"]))
            .order_by(Investigation.started_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )
    items: list[dict[str, Any]] = []
    for investigation in investigations:
        case = session.get(Case, investigation.case_id)
        if case is None:
            continue
        if investigation.status == "failed":
            reason = "Investigation failed - see the execution trace."
        elif investigation.escalation_reasons:
            reason = investigation.escalation_reasons[0]
        else:
            reason = "Awaiting analyst review."
        items.append(
            {
                "case_id": case.id,
                "investigation_id": investigation.id,
                "reference": case.reference,
                "organisation": case.organisation,
                "status": investigation.status,
                "overall_level": investigation.overall_level,
                "reason": reason,
                "escalations": investigation.escalation_reasons,
            }
        )
    return items


def recent_investigations(session: Session, *, limit: int = 10) -> list[dict[str, Any]]:
    investigations = (
        session.execute(
            select(Investigation).order_by(Investigation.started_at.desc()).limit(limit)
        )
        .scalars()
        .all()
    )
    out: list[dict[str, Any]] = []
    for investigation in investigations:
        case = session.get(Case, investigation.case_id)
        out.append(
            {
                "id": investigation.id,
                "case_id": investigation.case_id,
                "reference": case.reference if case else "",
                "organisation": case.organisation if case else "",
                "status": investigation.status,
                "overall_level": investigation.overall_level,
                "overall_score": investigation.overall_score,
                "evidence_strength": investigation.evidence_strength,
                "findings": len(investigation.risks),
                "duration_ms": investigation.duration_ms,
                "demo_mode": investigation.demo_mode,
                "started_at": investigation.started_at.isoformat(),
            }
        )
    return out


def system_health(session: Session) -> dict[str, Any]:
    """Step-level reliability, which is what "health" means for this system."""
    steps = session.execute(select(InvestigationStep)).scalars().all()
    if not steps:
        return {
            "steps_executed": 0,
            "failed_steps": 0,
            "retried_steps": 0,
            "success_rate": 0.0,
            "schema_retry_rate": 0.0,
        }
    failed = sum(1 for s in steps if s.status == "failed")
    retried = sum(1 for s in steps if s.retries > 0)
    return {
        "steps_executed": len(steps),
        "failed_steps": failed,
        "retried_steps": retried,
        "success_rate": round((len(steps) - failed) / len(steps), 3),
        "schema_retry_rate": round(retried / len(steps), 3),
    }


def operations_metrics(session: Session) -> dict[str, Any]:
    """Everything the AI Operations page renders."""
    investigations = session.execute(select(Investigation)).scalars().all()
    steps = session.execute(select(InvestigationStep)).scalars().all()

    by_capability: dict[str, dict[str, Any]] = {}
    for step in steps:
        bucket = by_capability.setdefault(
            step.capability,
            {
                "capability": step.capability,
                "executions": 0,
                "failures": 0,
                "retries": 0,
                "total_duration_ms": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            },
        )
        bucket["executions"] += 1
        bucket["failures"] += 1 if step.status == "failed" else 0
        bucket["retries"] += step.retries
        bucket["total_duration_ms"] += step.duration_ms
        bucket["input_tokens"] += step.input_tokens
        bucket["output_tokens"] += step.output_tokens
        bucket["cost_usd"] += step.cost_usd

    for bucket in by_capability.values():
        executions = bucket["executions"] or 1
        bucket["avg_duration_ms"] = int(bucket["total_duration_ms"] / executions)
        bucket["cost_usd"] = _round(bucket["cost_usd"], 5)

    llm_steps = [s for s in steps if s.model]
    latest_eval = session.execute(
        select(EvalRun).order_by(EvalRun.created_at.desc()).limit(1)
    ).scalar_one_or_none()

    return {
        "totals": {
            "investigations": len(investigations),
            "steps": len(steps),
            "llm_calls": sum(max(s.attempts, 0) for s in llm_steps),
            "input_tokens": sum(s.input_tokens for s in steps),
            "output_tokens": sum(s.output_tokens for s in steps),
            "estimated_cost_usd": _round(sum(s.cost_usd for s in steps), 5),
            "failed_steps": sum(1 for s in steps if s.status == "failed"),
            "retries": sum(s.retries for s in steps),
            "replayed_steps": sum(1 for s in steps if s.replayed),
        },
        "by_capability": sorted(
            by_capability.values(), key=lambda b: b["executions"], reverse=True
        ),
        "overrides": override_metrics(session),
        "category_distribution": category_distribution(session),
        "health": system_health(session),
        "grounding": grounding_metrics(session),
        "latest_evaluation": (
            {
                "id": latest_eval.id,
                "created_at": latest_eval.created_at.isoformat(),
                "passed": latest_eval.passed,
                "failed": latest_eval.failed,
                "total": latest_eval.total_cases,
                "metrics": latest_eval.metrics,
            }
            if latest_eval
            else None
        ),
        "cost_is_estimate": True,
    }


def grounding_metrics(session: Session) -> dict[str, Any]:
    """How often the grounding control actually rejected something."""
    investigations = session.execute(select(Investigation)).scalars().all()
    kept = session.execute(select(func.count(Evidence.id))).scalar_one() or 0
    rejected = sum(len(i.rejected_evidence or []) for i in investigations)
    proposed = kept + rejected
    mean_score = session.execute(select(func.avg(Evidence.grounding_score))).scalar_one() or 0.0
    return {
        "evidence_proposed": proposed,
        "evidence_grounded": kept,
        "evidence_rejected": rejected,
        "rejection_rate": round(rejected / proposed, 3) if proposed else 0.0,
        "mean_grounding_score": _round(mean_score, 3),
    }


def investigation_detail_metrics(session: Session, investigation: Investigation) -> dict[str, Any]:
    """Per-investigation counts used on the case screen."""
    coverage = investigation.coverage or []
    return {
        "evidence": len(investigation.evidence),
        "findings": len(investigation.risks),
        "false_positives": sum(1 for r in investigation.risks if r.is_false_positive),
        "policy_matches": session.execute(
            select(func.count(PolicyMatchRow.id)).where(
                PolicyMatchRow.investigation_id == investigation.id
            )
        ).scalar_one()
        or 0,
        "challenges": session.execute(
            select(func.count(ChallengeRow.id)).where(
                ChallengeRow.investigation_id == investigation.id
            )
        ).scalar_one()
        or 0,
        "verifications": session.execute(
            select(func.count(VerificationRow.id)).where(
                VerificationRow.investigation_id == investigation.id
            )
        ).scalar_one()
        or 0,
        "rejected_evidence": len(investigation.rejected_evidence or []),
        "coverage_ratio": (
            round(sum(1 for c in coverage if c["status"] == "complete") / len(coverage), 3)
            if coverage
            else 0.0
        ),
        "retrieval_quality": investigation.retrieval_quality,
    }


def domain_catalogue() -> list[dict[str, Any]]:
    """Configured review domains, with implementation status stated plainly."""
    return [
        {
            "key": domain.key,
            "name": domain.name,
            "description": domain.description,
            "status": domain.status,
            "implemented": domain.implemented,
            "risk_categories": [c.value for c in domain.risk_categories],
            "policy_library": list(domain.policy_library),
            "expected_evidence": [
                {"key": e.key, "label": e.label, "required": e.required}
                for e in domain.expected_evidence
            ],
            "escalation_rules": [
                {"key": r.key, "label": r.label, "description": r.description}
                for r in domain.escalation_rules
            ],
        }
        for domain in list_domains()
    ]


__all__ = [
    "category_distribution",
    "coverage_ratio",
    "dashboard_summary",
    "domain_catalogue",
    "grounding_metrics",
    "investigation_detail_metrics",
    "operations_metrics",
    "recent_investigations",
    "risk_distribution",
    "system_health",
]

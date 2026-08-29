"""Append-only audit trail.

There is exactly one way to write to the audit table - :func:`record` - and no
way to update or delete a row anywhere in the application. Immutability here is
a property of the code, not a convention someone is asked to respect.

Actions are named constants rather than free strings so the audit log can be
filtered and aggregated reliably, and so a typo cannot quietly create a
parallel event type that nothing queries.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus_api.db.models import AuditEvent

# -- action vocabulary ------------------------------------------------------

CASE_CREATED = "case.created"
DOCUMENT_INGESTED = "document.ingested"
INVESTIGATION_STARTED = "investigation.started"
INVESTIGATION_STEP = "investigation.step"
INVESTIGATION_COMPLETED = "investigation.completed"
INVESTIGATION_FAILED = "investigation.failed"
EVIDENCE_RECORDED = "evidence.recorded"
EVIDENCE_REJECTED = "evidence.rejected"
FINDING_CREATED = "finding.created"
SEVERITY_OVERRIDDEN = "finding.severity_overridden"
LIKELIHOOD_OVERRIDDEN = "finding.likelihood_overridden"
FALSE_POSITIVE_MARKED = "finding.marked_false_positive"
NOTE_ADDED = "finding.note_added"
CHALLENGE_REQUESTED = "challenge.requested"
REVIEW_SUBMITTED = "review.submitted"
REPORT_GENERATED = "report.generated"
QUESTION_ASKED = "question.asked"
SCENARIO_RUN = "scenario.run"
EVALUATION_RUN = "evaluation.run"


def record(
    session: Session,
    *,
    case_id: str,
    actor: str,
    action: str,
    summary: str,
    investigation_id: str = "",
    actor_type: str = "human",
    entity_type: str = "",
    entity_id: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event. The only write path to the audit trail."""
    event = AuditEvent(
        case_id=case_id,
        investigation_id=investigation_id,
        actor=actor,
        actor_type=actor_type,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        before=before or {},
        after=after or {},
    )
    session.add(event)
    return event


def history(
    session: Session,
    *,
    case_id: str | None = None,
    investigation_id: str | None = None,
    limit: int = 200,
) -> list[AuditEvent]:
    """Read the trail, newest first."""
    statement = select(AuditEvent)
    if case_id:
        statement = statement.where(AuditEvent.case_id == case_id)
    if investigation_id:
        statement = statement.where(AuditEvent.investigation_id == investigation_id)
    statement = statement.order_by(AuditEvent.created_at.desc()).limit(limit)
    return list(session.execute(statement).scalars().all())


def serialise(event: AuditEvent) -> dict[str, Any]:
    """Render one event for the API."""
    return {
        "id": event.id,
        "case_id": event.case_id,
        "investigation_id": event.investigation_id,
        "actor": event.actor,
        "actor_type": event.actor_type,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "summary": event.summary,
        "before": event.before,
        "after": event.after,
        "created_at": event.created_at.isoformat(),
    }

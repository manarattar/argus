"""Case, document and investigation endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from argus_api.db.models import Case, Document, Investigation
from argus_api.db.session import get_db
from argus_api.serializers import (
    case_payload,
    document_payload,
    investigation_detail,
    investigation_summary,
)
from argus_api.services import audit
from argus_api.services.investigation import latest_investigation, run_investigation
from argus_api.services.report import build_report, render_pdf
from argus_api.services.runtime import get_embedder, get_llm_provider

router = APIRouter(prefix="/api/cases", tags=["cases"])

DbSession = Annotated[Session, Depends(get_db)]


class RunInvestigationRequest(BaseModel):
    actor: str = Field(default="analyst", max_length=120)


def _get_case(session: Session, case_id: str) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found.")
    return case


def _get_investigation(session: Session, investigation_id: str) -> Investigation:
    investigation = session.get(Investigation, investigation_id)
    if investigation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return investigation


@router.get("")
def list_cases(session: DbSession) -> dict[str, Any]:
    """All cases, newest first, each with its most recent investigation."""
    cases = session.execute(select(Case).order_by(Case.created_at.desc())).scalars().all()
    return {
        "cases": [
            case_payload(case, investigation=latest_investigation(session, case.id))
            for case in cases
        ]
    }


@router.get("/{case_id}")
def get_case(case_id: str, session: DbSession) -> dict[str, Any]:
    case = _get_case(session, case_id)
    investigation = latest_investigation(session, case.id)
    return {
        **case_payload(case, investigation=investigation),
        "documents": [document_payload(d) for d in case.documents],
        "investigations": [
            investigation_summary(i)
            for i in sorted(case.investigations, key=lambda i: i.started_at, reverse=True)
        ],
    }


@router.get("/{case_id}/documents/{document_id}")
def get_document(case_id: str, document_id: str, session: DbSession) -> dict[str, Any]:
    """Full document text, so a citation can be opened in context."""
    document = session.get(Document, document_id)
    if document is None or (document.case_id and document.case_id != case_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return {
        **document_payload(document),
        "content": document.content,
        "chunks": [
            {
                "chunk_id": c.id,
                "ordinal": c.ordinal,
                "citation_key": c.citation_key,
                "section_number": c.section_number,
                "section_title": c.section_title,
                "page": c.page,
                "text": c.text,
            }
            for c in sorted(document.chunks, key=lambda c: c.ordinal)
        ],
    }


@router.post("/{case_id}/investigations", status_code=status.HTTP_201_CREATED)
def start_investigation(
    case_id: str, payload: RunInvestigationRequest, session: DbSession
) -> dict[str, Any]:
    """Run the investigation graph synchronously and return the result.

    Synchronous by design for this prototype: a run takes seconds, and the
    alternative - a job queue plus polling - would add moving parts without
    changing anything the product demonstrates. The trade-off and what a
    production deployment would do instead are recorded in
    docs/architecture/overview.md.
    """
    case = _get_case(session, case_id)
    investigation = run_investigation(
        session,
        case=case,
        provider=get_llm_provider(),
        embedder=get_embedder(),
        actor=payload.actor,
    )
    session.commit()
    session.refresh(investigation)
    return investigation_detail(session, investigation)


@router.get("/{case_id}/investigations/{investigation_id}")
def get_investigation(case_id: str, investigation_id: str, session: DbSession) -> dict[str, Any]:
    investigation = _get_investigation(session, investigation_id)
    if investigation.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    return investigation_detail(session, investigation)


@router.get("/{case_id}/audit")
def get_audit_trail(case_id: str, session: DbSession, limit: int = 200) -> dict[str, Any]:
    _get_case(session, case_id)
    events = audit.history(session, case_id=case_id, limit=min(limit, 500))
    return {"events": [audit.serialise(e) for e in events]}


@router.get("/{case_id}/investigations/{investigation_id}/report")
def get_report(case_id: str, investigation_id: str, session: DbSession) -> dict[str, Any]:
    """The assessment report as Markdown."""
    investigation = _get_investigation(session, investigation_id)
    if investigation.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    bundle = build_report(session, investigation)
    audit.record(
        session,
        case_id=case_id,
        investigation_id=investigation_id,
        actor="analyst",
        action=audit.REPORT_GENERATED,
        summary="Assessment report generated.",
        entity_type="investigation",
        entity_id=investigation_id,
    )
    session.commit()
    return {
        "title": bundle.title,
        "reference": bundle.reference,
        "generated_at": bundle.generated_at.isoformat(),
        "sections": bundle.sections,
        "markdown": bundle.markdown,
    }


@router.get("/{case_id}/investigations/{investigation_id}/report.pdf")
def get_report_pdf(case_id: str, investigation_id: str, session: DbSession) -> Response:
    """The assessment report as a PDF."""
    investigation = _get_investigation(session, investigation_id)
    if investigation.case_id != case_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Investigation not found.")
    bundle = build_report(session, investigation)
    try:
        pdf = render_pdf(bundle)
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "PDF rendering is unavailable because ReportLab is not installed.",
        ) from exc

    filename = f"{bundle.reference}-assessment.pdf".replace("/", "-")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

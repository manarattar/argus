"""Running an investigation and persisting the result.

This is the seam between the AI layer and the application. The graph
(:mod:`ai.graphs.investigation`) knows nothing about the database; this module
knows nothing about prompts. It builds the agent context, runs the graph, writes
every output as rows, and appends the audit events.

The persistence order matters: steps and evidence are written even when the run
failed part-way, because a failed investigation with a visible trace is far more
useful to an operator than an empty record.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.agents.context import AgentContext
from ai.domain import get_domain
from ai.graphs.investigation import InvestigationRunner
from ai.graphs.state import CaseContext, DocumentRef, InvestigationState, new_state
from ai.providers.base import LLMProvider
from ai.retrieval.embeddings import EmbeddingProvider
from ai.schemas.enums import InvestigationStatus, StepStatus
from ai.scoring.engine import adjusted_score
from argus_api.db.models import (
    Case,
    ChallengeRow,
    Document,
    Evidence,
    Investigation,
    InvestigationStep,
    PolicyMatchRow,
    Risk,
    VerificationRow,
)
from argus_api.services import audit
from argus_api.services.corpus import build_index


def _case_context(case: Case, documents: list[Document]) -> CaseContext:
    return CaseContext(
        case_id=case.id,
        reference=case.reference,
        organisation=case.organisation,
        review_type=case.review_type,
        domain_key=case.domain_key,
        analyst=case.analyst,
        jurisdiction=case.jurisdiction,
        sector=case.sector,
        background=case.background,
        documents=[
            DocumentRef(document_id=d.id, name=d.name, doc_kind=d.doc_kind) for d in documents
        ],
    )


def run_investigation(
    session: Session,
    *,
    case: Case,
    provider: LLMProvider,
    embedder: EmbeddingProvider,
    actor: str = "system",
    max_attempts: int = 3,
    max_tokens: int = 4096,
    temperature: float = 0.0,
) -> Investigation:
    """Execute the full investigation graph for a case and persist everything.

    Args:
        session: Open database session; the caller commits.
        case: The case to investigate.
        provider: Model backend, live or replay.
        embedder: Embedding backend used to build the retrieval index.
        actor: Who initiated the run, recorded in the audit trail.

    Returns:
        The persisted :class:`Investigation`, in status
        ``awaiting_human_review`` on success or ``failed`` if the graph could
        not produce an assessment.
    """
    domain = get_domain(case.domain_key)
    documents = session.execute(select(Document).where(Document.case_id == case.id)).scalars().all()

    investigation = Investigation(
        case_id=case.id,
        status=InvestigationStatus.RUNNING.value,
        domain_key=domain.key,
        model_backend=provider.name,
        model_name=provider.model,
        demo_mode=not provider.live,
        embedding_model=embedder.name,
    )
    session.add(investigation)
    session.flush()

    audit.record(
        session,
        case_id=case.id,
        investigation_id=investigation.id,
        actor=actor,
        actor_type="system",
        action=audit.INVESTIGATION_STARTED,
        summary=(
            f"Investigation started for {case.organisation} using "
            f"{'recorded responses' if not provider.live else provider.model}."
        ),
        entity_type="investigation",
        entity_id=investigation.id,
    )

    index = build_index(session, embedder, case_id=case.id, include_policies=True)
    context = AgentContext(
        provider=provider,
        index=index,
        domain=domain,
        case_summary=_case_context(case, list(documents)).summary(),
        max_attempts=max_attempts,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    runner = InvestigationRunner(context, domain)
    started = time.perf_counter()
    state = runner.run(
        new_state(
            investigation_id=investigation.id,
            case=_case_context(case, list(documents)),
            domain_key=domain.key,
        )
    )
    duration_ms = int((time.perf_counter() - started) * 1000)

    _persist_steps(session, investigation, state["steps"])
    _persist_evidence(session, investigation, state["evidence"])
    _persist_risks(session, investigation, state)
    _persist_policy(session, investigation, state["policy_matches"])
    _persist_challenges(session, investigation, state["challenges"])
    _persist_verifications(session, investigation, state["verifications"])

    assessment = state.get("assessment")
    investigation.duration_ms = duration_ms
    investigation.retrieval_quality = state.get("retrieval_quality", 0.0)
    investigation.escalation_reasons = list(state.get("escalation_reasons", []))
    investigation.integrity = runner.integrity.to_dict()
    investigation.rejected_evidence = [r.to_dict() for r in state["rejected_evidence"]]
    investigation.errors = list(state.get("errors", []))
    investigation.total_input_tokens = sum(s.input_tokens for s in state["steps"])
    investigation.total_output_tokens = sum(s.output_tokens for s in state["steps"])
    investigation.total_cost_usd = round(sum(s.cost_usd for s in state["steps"]), 6)

    if assessment is not None:
        investigation.overall_level = assessment.overall_level.value
        investigation.overall_score = assessment.overall_score
        investigation.evidence_strength = assessment.evidence_strength.value
        investigation.score_factors = [f.model_dump() for f in assessment.score_factors]
        investigation.category_levels = {k: v.value for k, v in assessment.category_levels.items()}
        investigation.coverage = [
            {
                "category": c.category.value,
                "category_label": c.category.label,
                "status": c.status.value,
                "expected": c.expected,
                "found_evidence_ids": c.found_evidence_ids,
                "note": c.note,
            }
            for c in assessment.coverage
        ]
        investigation.narrative = assessment.narrative.model_dump(mode="json")
        investigation.status = InvestigationStatus.AWAITING_HUMAN_REVIEW.value
        case.status = "awaiting_review"
    elif state.get("status") == "failed":
        investigation.status = InvestigationStatus.FAILED.value
        case.status = "investigating"
    else:
        # The graph reached the gate but synthesis did not produce a narrative.
        # The computed rating still stands and the UI reports the missing
        # narrative rather than covering for it.
        investigation.status = InvestigationStatus.AWAITING_HUMAN_REVIEW.value
        case.status = "awaiting_review"

    investigation.completed_at = datetime.now(UTC)

    audit.record(
        session,
        case_id=case.id,
        investigation_id=investigation.id,
        actor=actor,
        actor_type="ai",
        action=(
            audit.INVESTIGATION_FAILED
            if investigation.status == InvestigationStatus.FAILED.value
            else audit.INVESTIGATION_COMPLETED
        ),
        summary=(
            f"Investigation finished with provisional rating "
            f"{investigation.overall_level or 'none'} "
            f"({investigation.overall_score:.0f}/100) from "
            f"{len(state['risks'])} finding(s) and {len(state['evidence'])} "
            f"grounded evidence item(s)."
        ),
        entity_type="investigation",
        entity_id=investigation.id,
        after={
            "overall_level": investigation.overall_level,
            "overall_score": investigation.overall_score,
            "findings": len(state["risks"]),
            "evidence": len(state["evidence"]),
            "errors": investigation.errors,
        },
    )

    session.flush()
    return investigation


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _persist_steps(session: Session, inv: Investigation, steps: list[Any]) -> None:
    for ordinal, step in enumerate(steps):
        session.add(
            InvestigationStep(
                investigation_id=inv.id,
                step_id=step.step_id,
                ordinal=ordinal,
                name=step.name,
                capability=step.capability,
                status=step.status.value,
                summary=step.summary,
                detail=step.detail,
                prompt_reference=step.prompt_reference,
                model=step.model,
                attempts=step.attempts,
                retries=step.retries,
                input_tokens=step.input_tokens,
                output_tokens=step.output_tokens,
                cost_usd=step.cost_usd,
                duration_ms=step.duration_ms,
                replayed=step.replayed,
                error=step.error,
                started_at=step.started_at,
            )
        )


def _persist_evidence(session: Session, inv: Investigation, items: list[Any]) -> None:
    for item in items:
        session.add(
            Evidence(
                id=f"{inv.id}:{item.evidence_id}",
                investigation_id=inv.id,
                evidence_id=item.evidence_id,
                statement=item.statement,
                quote=item.quote,
                kind=item.kind.value,
                category=item.category.value,
                document_id=item.document_id,
                document_name=item.document_name,
                section_reference=item.section_reference,
                chunk_id=item.chunk_id,
                materiality=item.materiality.value,
                grounding_score=item.grounding_score,
                is_grounded=item.is_grounded,
            )
        )


def _persist_risks(session: Session, inv: Investigation, state: InvestigationState) -> None:
    assessment = state.get("assessment")
    mind_changers = {}
    if assessment is not None:
        mind_changers = {m.risk_id: m for m in assessment.narrative.mind_changers}

    for finding in state["risks"]:
        changer = mind_changers.get(finding.risk_id)
        session.add(
            Risk(
                id=f"{inv.id}:{finding.risk_id}",
                investigation_id=inv.id,
                risk_id=finding.risk_id,
                title=finding.title,
                category=finding.category.value,
                description=finding.description,
                ai_severity=finding.severity.value,
                ai_likelihood=finding.likelihood.value,
                severity=finding.severity.value,
                likelihood=finding.likelihood.value,
                supporting_evidence_ids=list(finding.supporting_evidence_ids),
                contradicting_evidence_ids=list(finding.contradicting_evidence_ids),
                assumptions=list(finding.assumptions),
                open_questions=list(finding.open_questions),
                mitigating_factors=list(finding.mitigating_factors),
                evidence_strength=finding.evidence_strength.value,
                strength_rationale=finding.strength_rationale,
                inherent_score=finding.inherent_score,
                adjusted_score=adjusted_score(finding),
                mind_changer_increase=changer.would_increase if changer else "",
                mind_changer_decrease=changer.would_decrease if changer else "",
            )
        )


def _persist_policy(session: Session, inv: Investigation, matches: list[Any]) -> None:
    for match in matches:
        session.add(
            PolicyMatchRow(
                id=f"{inv.id}:{match.match_id}",
                investigation_id=inv.id,
                match_id=match.match_id,
                risk_id=match.risk_id,
                policy_id=match.policy_id,
                clause_reference=match.clause_reference,
                clause_title=match.clause_title,
                relevance=match.relevance,
                trigger_type=match.trigger_type,
                threshold_assessment=match.threshold_assessment,
                sufficiency_caveat=match.sufficiency_caveat,
            )
        )


def _persist_challenges(session: Session, inv: Investigation, challenges: list[Any]) -> None:
    for challenge in challenges:
        session.add(
            ChallengeRow(
                id=f"{inv.id}:{challenge.challenge_id}",
                investigation_id=inv.id,
                challenge_id=challenge.challenge_id,
                risk_id=challenge.risk_id,
                challenge_type=challenge.challenge_type,
                argument=challenge.argument,
                counter_evidence_ids=list(challenge.counter_evidence_ids),
                suggested_revision=challenge.suggested_revision,
                proposed_severity=(
                    challenge.proposed_severity.value if challenge.proposed_severity else ""
                ),
                unresolved=challenge.unresolved,
            )
        )


def _persist_verifications(session: Session, inv: Investigation, verifications: list[Any]) -> None:
    for verification in verifications:
        session.add(
            VerificationRow(
                id=f"{inv.id}:{verification.verification_id}",
                investigation_id=inv.id,
                verification_id=verification.verification_id,
                risk_id=verification.risk_id,
                claim=verification.claim,
                status=verification.status.value,
                reasoning=verification.reasoning,
                citations_checked=list(verification.citations_checked),
                irrelevant_citation_ids=list(verification.irrelevant_citation_ids),
                downgrade_recommended=verification.downgrade_recommended,
            )
        )


def latest_investigation(session: Session, case_id: str) -> Investigation | None:
    return session.execute(
        select(Investigation)
        .where(Investigation.case_id == case_id)
        .order_by(Investigation.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def step_is_failed(step: InvestigationStep) -> bool:
    return step.status == StepStatus.FAILED.value

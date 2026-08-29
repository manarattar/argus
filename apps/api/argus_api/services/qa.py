"""Ask ARGUS and on-demand challenge.

Both capabilities answer from the case record only. They retrieve the evidence,
findings, policy matches and challenges already stored for the investigation and
put that in front of the model as untrusted, citable material.

The important behaviour is the refusal path. When the record does not answer the
question, the model is required to say so via ``answerable=false`` rather than
reach for general knowledge. Any citation it returns is then checked against
stored evidence ids before the answer is returned, so a citation that does not
resolve is stripped rather than shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.agents.context import (
    render_challenges,
    render_evidence,
    render_policy_matches,
    render_risks,
)
from ai.prompts.library import ASK_ARGUS, CHALLENGE_ON_DEMAND
from ai.providers.base import LLMProvider
from ai.providers.structured import StructuredResult, generate_structured
from ai.schemas.enums import EvidenceKind, Likelihood, RiskCategory, Severity
from ai.schemas.models import (
    Challenge,
    ChallengeReport,
    EvidenceItem,
    GroundedAnswer,
    PolicyMatch,
    RiskFinding,
)
from argus_api.db.models import ChallengeRow, Evidence, Investigation, PolicyMatchRow, Risk

MAX_QUESTION_LENGTH = 600


class QuestionError(ValueError):
    """The question could not be accepted."""


@dataclass
class AnswerResult:
    answer: GroundedAnswer
    result: StructuredResult[GroundedAnswer]


def _evidence_models(session: Session, investigation: Investigation) -> list[EvidenceItem]:
    rows = (
        session.execute(select(Evidence).where(Evidence.investigation_id == investigation.id))
        .scalars()
        .all()
    )
    return [
        EvidenceItem(
            evidence_id=row.evidence_id,
            statement=row.statement,
            quote=row.quote,
            kind=EvidenceKind(row.kind),
            category=RiskCategory(row.category),
            document_id=row.document_id,
            document_name=row.document_name,
            section_reference=row.section_reference,
            chunk_id=row.chunk_id,
            materiality=Severity(row.materiality),
            grounding_score=row.grounding_score,
            is_grounded=row.is_grounded,
        )
        for row in rows
    ]


def _risk_models(investigation: Investigation) -> list[RiskFinding]:
    return [
        RiskFinding(
            risk_id=row.risk_id,
            title=row.title,
            category=RiskCategory(row.category),
            description=row.description,
            severity=Severity(row.severity),
            likelihood=Likelihood(row.likelihood),
            supporting_evidence_ids=list(row.supporting_evidence_ids),
            contradicting_evidence_ids=list(row.contradicting_evidence_ids),
            assumptions=list(row.assumptions),
            open_questions=list(row.open_questions),
            mitigating_factors=list(row.mitigating_factors),
        )
        for row in investigation.risks
    ]


def _policy_models(session: Session, investigation: Investigation) -> list[PolicyMatch]:
    rows = (
        session.execute(
            select(PolicyMatchRow).where(PolicyMatchRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    return [
        PolicyMatch(
            match_id=row.match_id,
            risk_id=row.risk_id,
            policy_id=row.policy_id,
            clause_reference=row.clause_reference,
            clause_title=row.clause_title,
            relevance=row.relevance,
            trigger_type=row.trigger_type,
            threshold_assessment=row.threshold_assessment,
            sufficiency_caveat=row.sufficiency_caveat,
        )
        for row in rows
    ]


def _challenge_models(session: Session, investigation: Investigation) -> list[Challenge]:
    rows = (
        session.execute(
            select(ChallengeRow).where(ChallengeRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    return [
        Challenge(
            challenge_id=row.challenge_id,
            risk_id=row.risk_id,
            challenge_type=row.challenge_type,
            argument=row.argument,
            counter_evidence_ids=list(row.counter_evidence_ids),
            suggested_revision=row.suggested_revision,
            proposed_severity=Severity(row.proposed_severity) if row.proposed_severity else None,
            unresolved=row.unresolved,
        )
        for row in rows
    ]


def answer_question(
    session: Session,
    investigation: Investigation,
    *,
    question: str,
    provider: LLMProvider,
    max_attempts: int = 3,
) -> AnswerResult:
    """Answer an analyst question from the case record.

    Raises:
        QuestionError: The question is empty or over the length limit.
    """
    question = question.strip()
    if not question:
        raise QuestionError("The question is empty.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise QuestionError(f"Questions are limited to {MAX_QUESTION_LENGTH} characters.")

    evidence = _evidence_models(session, investigation)
    risks = _risk_models(investigation)

    assessment_block = (
        f"Overall provisional rating: {investigation.overall_level or 'not rated'} "
        f"({investigation.overall_score:.0f}/100)\n"
        f"Portfolio evidence strength: {investigation.evidence_strength or 'unknown'}\n"
        "Scoring factors:\n"
        + "\n".join(
            f"- {f.get('label')}: {f.get('contribution'):+.1f} ({f.get('direction')}) "
            f"- {f.get('detail')}"
            for f in (investigation.score_factors or [])
        )
    )

    user = f"""\
## Analyst question
{question}

## Current assessment
{assessment_block}

## Findings
{render_risks(risks)}

## Policy matches
{render_policy_matches(_policy_models(session, investigation))}

## Challenges raised
{render_challenges(_challenge_models(session, investigation))}

## Case evidence
{render_evidence(evidence)}

Answer using only the material above. Cite the evidence ids that support your
answer and include each quote. If the material does not answer the question, set
answerable to false and say what is missing."""

    result = generate_structured(
        provider,
        GroundedAnswer,
        system=ASK_ARGUS.system,
        user=user,
        purpose="ask",
        max_attempts=max_attempts,
        max_tokens=2048,
    )

    # Citations must resolve to stored evidence; anything else is removed.
    by_id = {e.evidence_id: e for e in evidence}
    clean = [c for c in result.value.citations if c.evidence_id in by_id]
    answer = result.value.model_copy(update={"citations": clean})
    return AnswerResult(answer=answer, result=result)


def challenge_on_demand(
    session: Session,
    investigation: Investigation,
    *,
    risk: Risk,
    provider: LLMProvider,
    max_attempts: int = 3,
) -> tuple[list[Challenge], StructuredResult[ChallengeReport]]:
    """Build the strongest evidence-based case against one finding."""
    evidence = _evidence_models(session, investigation)
    target = next((r for r in _risk_models(investigation) if r.risk_id == risk.risk_id), None)
    if target is None:
        raise QuestionError("That finding is not part of this investigation.")

    user = f"""\
## Finding selected by the analyst
{render_risks([target])}

## Complete evidence set
{render_evidence(evidence)}

Construct the strongest evidence-based argument against this finding. Cite
counter-evidence ids where they exist. If the finding is in fact well-founded,
say so and explain what makes it hold."""

    result = generate_structured(
        provider,
        ChallengeReport,
        system=CHALLENGE_ON_DEMAND.system,
        user=user,
        purpose="challenge_on_demand",
        max_attempts=max_attempts,
        max_tokens=2048,
    )

    valid_ids = {e.evidence_id for e in evidence}
    challenges = [
        c.model_copy(
            update={
                "risk_id": risk.risk_id,
                "counter_evidence_ids": [e for e in c.counter_evidence_ids if e in valid_ids],
            }
        )
        for c in result.value.challenges
    ]
    return challenges, result


def serialise_answer(answer: GroundedAnswer) -> dict[str, Any]:
    return {
        "answer": answer.answer,
        "answerable": answer.answerable,
        "insufficient_evidence_note": answer.insufficient_evidence_note,
        "citations": [
            {
                "evidence_id": c.evidence_id,
                "document_name": c.document_name,
                "section_reference": c.section_reference,
                "quote": c.quote,
            }
            for c in answer.citations
        ],
    }

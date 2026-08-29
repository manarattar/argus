"""Investigation state and execution trace.

The state is the single object every node reads from and writes to, which is
what makes the workflow inspectable: at any point, the complete condition of an
investigation is one serialisable value. That is also what allows the graph to
be interrupted for human review and resumed later, potentially in a different
process.

The trace deserves a note. It records what each step *did* - which capability
ran, which tool it used, how much it retrieved, how long it took, what it cost -
and never the model's private reasoning. That boundary is deliberate: an
operator needs to see the process to trust and debug it, and exposing a model's
intermediate reasoning to end users is both a leakage risk and a poor basis for
a decision. The UI renders these entries; there is nothing else behind them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypedDict

from ai.schemas.enums import StepStatus
from ai.schemas.models import (
    Challenge,
    ClaimVerification,
    CoverageItem,
    EvidenceItem,
    InvestigationPlan,
    PolicyMatch,
    RiskAssessment,
    RiskFinding,
)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class StepTrace:
    """One executed node, as shown on the investigation timeline."""

    step_id: str
    name: str
    capability: str
    status: StepStatus = StepStatus.PENDING
    started_at: datetime = field(default_factory=_now)
    finished_at: datetime | None = None
    summary: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    prompt_reference: str = ""
    model: str = ""
    attempts: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    replayed: bool = False
    error: str = ""
    retries: int = 0

    @property
    def duration_ms(self) -> int:
        if self.finished_at is None:
            return 0
        return int((self.finished_at - self.started_at).total_seconds() * 1000)

    def finish(self, status: StepStatus, summary: str, **detail: Any) -> StepTrace:
        self.status = status
        self.summary = summary
        self.finished_at = _now()
        self.detail.update(detail)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "capability": self.capability,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "detail": self.detail,
            "prompt_reference": self.prompt_reference,
            "model": self.model,
            "attempts": self.attempts,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
            "replayed": self.replayed,
            "error": self.error,
            "retries": self.retries,
        }


@dataclass
class RejectedEvidence:
    """Evidence discarded by a control, kept so the rejection is auditable.

    Silently dropping a model's output would make the pipeline look cleaner than
    it is. Retaining rejects lets the Evaluation Lab report how often the
    grounding check actually fires, which is one of the few honest measures of
    how much the control is doing.
    """

    evidence_id: str
    statement: str
    reason: str
    grounding_score: float = 0.0
    cited_chunk_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "statement": self.statement,
            "reason": self.reason,
            "grounding_score": self.grounding_score,
            "cited_chunk_id": self.cited_chunk_id,
        }


@dataclass
class DocumentRef:
    """A case document as the graph sees it."""

    document_id: str
    name: str
    doc_kind: str = "case"
    description: str = ""


@dataclass
class CaseContext:
    """Immutable case facts handed to the graph."""

    case_id: str
    reference: str
    organisation: str
    review_type: str
    domain_key: str
    analyst: str
    jurisdiction: str = ""
    sector: str = ""
    background: str = ""
    documents: list[DocumentRef] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Case reference: {self.reference}",
            f"Subject organisation: {self.organisation}",
            f"Review type: {self.review_type}",
            f"Assigned analyst: {self.analyst}",
        ]
        if self.sector:
            lines.append(f"Sector: {self.sector}")
        if self.jurisdiction:
            lines.append(f"Jurisdiction: {self.jurisdiction}")
        if self.background:
            lines.append(f"Background: {self.background}")
        return "\n".join(lines)


class InvestigationState(TypedDict, total=False):
    """State threaded through the investigation graph."""

    # -- inputs (set once) --
    investigation_id: str
    case: CaseContext
    domain_key: str

    # -- produced by nodes --
    plan: InvestigationPlan | None
    evidence: list[EvidenceItem]
    rejected_evidence: list[RejectedEvidence]
    risks: list[RiskFinding]
    policy_matches: list[PolicyMatch]
    challenges: list[Challenge]
    verifications: list[ClaimVerification]
    coverage: list[CoverageItem]
    assessment: RiskAssessment | None

    # -- bookkeeping --
    steps: list[StepTrace]
    errors: list[str]
    status: str
    retrieval_quality: float
    escalation_reasons: list[str]


def new_state(*, investigation_id: str, case: CaseContext, domain_key: str) -> InvestigationState:
    """Create an empty state for a fresh investigation."""
    return InvestigationState(
        investigation_id=investigation_id,
        case=case,
        domain_key=domain_key,
        plan=None,
        evidence=[],
        rejected_evidence=[],
        risks=[],
        policy_matches=[],
        challenges=[],
        verifications=[],
        coverage=[],
        assessment=None,
        steps=[],
        errors=[],
        status="pending",
        retrieval_quality=0.0,
        escalation_reasons=[],
    )

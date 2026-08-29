"""Relational model.

Design notes worth stating:

* **Agent output is persisted as first-class rows, not JSON blobs.** Evidence,
  findings, policy matches, challenges and verifications each get a table with
  real foreign keys. That is what makes the Evidence Graph a query rather than a
  parsing exercise, and what lets the audit trail reference a specific finding.
* **The audit trail is append-only by construction.** :class:`AuditEvent` has no
  update path anywhere in the application; the service layer only ever inserts.
  Immutability is enforced at the database level in a real deployment (see
  docs/architecture/data.md); here it is enforced by having written no code that
  can mutate it.
* **Human overrides are stored beside the AI recommendation they replaced**,
  never instead of it. Losing the original would destroy the only measurement of
  how often the system is wrong.
* **Embeddings are stored portably.** SQLite gets a JSON array, Postgres gets a
  ``vector`` column when pgvector is available. The retrieval interface is
  identical either way, so the storage choice never leaks into agent code.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base with JSON portability across SQLite and Postgres."""

    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


# ---------------------------------------------------------------------------
# Case and documents
# ---------------------------------------------------------------------------


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    organisation: Mapped[str] = mapped_column(String(200))
    review_type: Mapped[str] = mapped_column(String(120))
    domain_key: Mapped[str] = mapped_column(String(64), default="counterparty_review")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    analyst: Mapped[str] = mapped_column(String(120))
    sector: Mapped[str] = mapped_column(String(120), default="")
    jurisdiction: Mapped[str] = mapped_column(String(120), default="")
    background: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    documents: Mapped[list[Document]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )
    investigations: Mapped[list[Investigation]] = relationship(
        back_populates="case", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    doc_kind: Mapped[str] = mapped_column(String(16), default="case", index=True)
    # Short code such as CRF or GOS, used to build deterministic policy citations.
    code: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    case: Mapped[Case | None] = relationship(back_populates="documents")
    chunks: Mapped[list[Chunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    section_number: Mapped[str] = mapped_column(String(32), default="")
    section_title: Mapped[str] = mapped_column(String(200), default="")
    citation_key: Mapped[str] = mapped_column(String(120), default="")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON on SQLite; migrated to a pgvector column when Postgres is configured.
    embedding: Mapped[list[Any]] = mapped_column(JSON, default=list)
    embedding_model: Mapped[str] = mapped_column(String(64), default="")

    document: Mapped[Document] = relationship(back_populates="chunks")


# ---------------------------------------------------------------------------
# Investigation and its outputs
# ---------------------------------------------------------------------------


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    domain_key: Mapped[str] = mapped_column(String(64), default="counterparty_review")
    model_backend: Mapped[str] = mapped_column(String(64), default="")
    model_name: Mapped[str] = mapped_column(String(64), default="")
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    retrieval_quality: Mapped[float] = mapped_column(Float, default=0.0)
    embedding_model: Mapped[str] = mapped_column(String(64), default="")

    overall_level: Mapped[str] = mapped_column(String(16), default="")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_strength: Mapped[str] = mapped_column(String(16), default="")
    score_factors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    category_levels: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    coverage: Mapped[list[Any]] = mapped_column(JSON, default=list)
    narrative: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    escalation_reasons: Mapped[list[Any]] = mapped_column(JSON, default=list)
    integrity: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rejected_evidence: Mapped[list[Any]] = mapped_column(JSON, default=list)
    errors: Mapped[list[Any]] = mapped_column(JSON, default=list)

    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped[Case] = relationship(back_populates="investigations")
    steps: Mapped[list[InvestigationStep]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    evidence: Mapped[list[Evidence]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )
    risks: Mapped[list[Risk]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan"
    )


class InvestigationStep(Base):
    __tablename__ = "investigation_steps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(120))
    capability: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    summary: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    prompt_reference: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(64), default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    retries: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    replayed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    investigation: Mapped[Investigation] = relationship(back_populates="steps")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    evidence_id: Mapped[str] = mapped_column(String(64), index=True)
    statement: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="fact")
    category: Mapped[str] = mapped_column(String(32), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    document_name: Mapped[str] = mapped_column(String(200))
    section_reference: Mapped[str] = mapped_column(String(120))
    chunk_id: Mapped[str] = mapped_column(String(96))
    materiality: Mapped[str] = mapped_column(String(20), default="moderate")
    grounding_score: Mapped[float] = mapped_column(Float, default=0.0)
    is_grounded: Mapped[bool] = mapped_column(Boolean, default=True)

    investigation: Mapped[Investigation] = relationship(back_populates="evidence")


class Risk(Base):
    __tablename__ = "risks"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    risk_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text)

    # The AI's recommendation, preserved verbatim even after a human override.
    ai_severity: Mapped[str] = mapped_column(String(20))
    ai_likelihood: Mapped[str] = mapped_column(String(20))
    # Current effective values - equal to the AI values until someone changes them.
    severity: Mapped[str] = mapped_column(String(20))
    likelihood: Mapped[str] = mapped_column(String(20))

    supporting_evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    contradicting_evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    assumptions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    open_questions: Mapped[list[Any]] = mapped_column(JSON, default=list)
    mitigating_factors: Mapped[list[Any]] = mapped_column(JSON, default=list)
    evidence_strength: Mapped[str] = mapped_column(String(20), default="insufficient")
    strength_rationale: Mapped[str] = mapped_column(Text, default="")
    inherent_score: Mapped[float] = mapped_column(Float, default=0.0)
    adjusted_score: Mapped[float] = mapped_column(Float, default=0.0)
    mind_changer_increase: Mapped[str] = mapped_column(Text, default="")
    mind_changer_decrease: Mapped[str] = mapped_column(Text, default="")

    is_false_positive: Mapped[bool] = mapped_column(Boolean, default=False)
    analyst_note: Mapped[str] = mapped_column(Text, default="")

    investigation: Mapped[Investigation] = relationship(back_populates="risks")


class PolicyMatchRow(Base):
    __tablename__ = "policy_matches"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    match_id: Mapped[str] = mapped_column(String(64))
    risk_id: Mapped[str] = mapped_column(String(64), index=True)
    policy_id: Mapped[str] = mapped_column(String(64))
    clause_reference: Mapped[str] = mapped_column(String(60), index=True)
    clause_title: Mapped[str] = mapped_column(String(200))
    relevance: Mapped[str] = mapped_column(Text)
    trigger_type: Mapped[str] = mapped_column(String(32), index=True)
    threshold_assessment: Mapped[str] = mapped_column(Text, default="")
    sufficiency_caveat: Mapped[str] = mapped_column(Text, default="")


class ChallengeRow(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    challenge_id: Mapped[str] = mapped_column(String(64))
    risk_id: Mapped[str] = mapped_column(String(64), index=True)
    challenge_type: Mapped[str] = mapped_column(String(40), index=True)
    argument: Mapped[str] = mapped_column(Text)
    counter_evidence_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    suggested_revision: Mapped[str] = mapped_column(Text, default="")
    proposed_severity: Mapped[str] = mapped_column(String(20), default="")
    unresolved: Mapped[bool] = mapped_column(Boolean, default=False)
    on_demand: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class VerificationRow(Base):
    __tablename__ = "verifications"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    verification_id: Mapped[str] = mapped_column(String(64))
    risk_id: Mapped[str] = mapped_column(String(64), index=True)
    claim: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reasoning: Mapped[str] = mapped_column(Text)
    citations_checked: Mapped[list[Any]] = mapped_column(JSON, default=list)
    irrelevant_citation_ids: Mapped[list[Any]] = mapped_column(JSON, default=list)
    downgrade_recommended: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Human oversight
# ---------------------------------------------------------------------------


class Override(Base):
    """A recorded human decision that differs from the AI recommendation.

    Both sides are stored. The override rate computed from this table is the
    single most useful adoption metric ARGUS produces: a rate near zero suggests
    analysts are rubber-stamping, and a very high rate suggests the model is not
    earning its place.
    """

    __tablename__ = "overrides"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    risk_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    field: Mapped[str] = mapped_column(String(40))
    ai_value: Mapped[str] = mapped_column(String(120))
    human_value: Mapped[str] = mapped_column(String(120))
    rationale: Mapped[str] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Review(Base):
    """The human review decision that releases an investigation."""

    __tablename__ = "reviews"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    investigation_id: Mapped[str] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(40), index=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    actor: Mapped[str] = mapped_column(String(120))
    ai_overall_level: Mapped[str] = mapped_column(String(16), default="")
    final_overall_level: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    """Append-only record of everything that happened to a case."""

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(String(32), index=True)
    investigation_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    actor: Mapped[str] = mapped_column(String(120))
    actor_type: Mapped[str] = mapped_column(String(16), default="human")
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(96), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    after: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


Index("ix_audit_case_time", AuditEvent.case_id, AuditEvent.created_at)


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    suite: Mapped[str] = mapped_column(String(64), default="default")
    model_backend: Mapped[str] = mapped_column(String(64), default="")
    model_name: Mapped[str] = mapped_column(String(64), default="")
    embedding_model: Mapped[str] = mapped_column(String(64), default="")
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    errored: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    results: Mapped[list[EvalResult]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id", ondelete="CASCADE"), index=True)
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    suite: Mapped[str] = mapped_column(String(64), index=True)
    category: Mapped[str] = mapped_column(String(48), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    expected: Mapped[str] = mapped_column(Text, default="")
    actual: Mapped[str] = mapped_column(Text, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    run: Mapped[EvalRun] = relationship(back_populates="results")

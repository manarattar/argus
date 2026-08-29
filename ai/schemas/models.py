"""Structured outputs exchanged between ARGUS agents.

Design rules enforced here:

1. **Every agent returns a validated model, never prose.** Prompts request
   JSON; :mod:`ai.providers.structured` validates it and retries with the
   validation error appended. A response that never validates fails the step
   loudly instead of degrading into free text.
2. **Citations are identifiers, not sentences.** Agents may only reference
   evidence by ``evidence_id``. Cross-reference integrity is then a
   deterministic set-membership check (see :mod:`ai.graphs.integrity`), which
   is what makes "no fabricated citations" a testable property rather than a
   hope.
3. **Confidence is never a bare float from the model.** Models supply ordinal,
   defensible signals; numeric bands are computed downstream by
   :mod:`ai.scoring.uncertainty`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ai.schemas.enums import (
    CoverageStatus,
    EvidenceKind,
    EvidenceStrength,
    Likelihood,
    RiskCategory,
    RiskLevel,
    Severity,
    SupportStatus,
)

# An identifier the model is allowed to mint, constrained enough that a
# hallucinated free-text citation fails validation rather than reaching the UI.
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ArgusModel(BaseModel):
    """Base model: reject unknown keys so prompt drift surfaces immediately."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------
# Agent 1 - Intake & Planning
# --------------------------------------------------------------------------


class PlannedTask(ArgusModel):
    """One unit of analysis the planner believes the case requires."""

    task_id: Identifier
    objective: str = Field(min_length=10, max_length=400)
    capability: str = Field(
        max_length=64,
        description=(
            "Reusable capability that should execute this task, e.g. "
            "evidence_extraction, policy_retrieval, risk_analysis."
        ),
    )
    focus_categories: list[RiskCategory] = Field(default_factory=list, max_length=10)
    rationale: str = Field(min_length=10, max_length=600)


class InformationGap(ArgusModel):
    """A document or data point the planner expected but did not find."""

    gap_id: Identifier
    description: str = Field(min_length=10, max_length=400)
    why_it_matters: str = Field(min_length=10, max_length=400)
    blocks_categories: list[RiskCategory] = Field(default_factory=list, max_length=10)


class InvestigationPlan(ArgusModel):
    """Output of Agent 1. Drives which downstream capabilities actually run."""

    objective: str = Field(min_length=20, max_length=800)
    scope_summary: str = Field(min_length=20, max_length=1200)
    tasks: list[PlannedTask] = Field(min_length=1, max_length=12)
    priority_categories: list[RiskCategory] = Field(min_length=1, max_length=10)
    information_gaps: list[InformationGap] = Field(default_factory=list, max_length=12)

    @field_validator("tasks")
    @classmethod
    def _unique_task_ids(cls, tasks: list[PlannedTask]) -> list[PlannedTask]:
        ids = [t.task_id for t in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task_id values must be unique within a plan")
        return tasks


# --------------------------------------------------------------------------
# Agent 2 - Evidence Extraction
# --------------------------------------------------------------------------


class EvidenceItem(ArgusModel):
    """A single material statement lifted from a source document.

    ``quote`` must be a verbatim span of the cited chunk. The extractor is told
    this, but it is *enforced* by
    :func:`ai.tools.grounding.score_quote_grounding`, which re-reads the stored
    chunk text. Evidence whose quote cannot be located is rejected before it
    reaches the risk agent - the single most important anti-hallucination
    control in the pipeline.
    """

    evidence_id: Identifier
    statement: str = Field(
        min_length=10,
        max_length=600,
        description="Normalised, self-contained restatement of the finding.",
    )
    quote: str = Field(
        min_length=8,
        max_length=800,
        description="Verbatim span copied from the source chunk.",
    )
    kind: EvidenceKind = EvidenceKind.FACT
    category: RiskCategory
    document_id: Identifier
    document_name: str = Field(min_length=1, max_length=200)
    section_reference: str = Field(
        min_length=1,
        max_length=120,
        description="Human-citable locator, e.g. 'p. 12, 3.1'.",
    )
    chunk_id: Identifier
    materiality: Severity = Field(
        default=Severity.MODERATE,
        description="How consequential this single data point is on its own.",
    )
    extracted_at: datetime = Field(default_factory=_utcnow)

    # Populated by deterministic post-processing, never by the model.
    grounding_score: float = Field(default=0.0, ge=0.0, le=1.0)
    is_grounded: bool = False


class EvidenceExtraction(ArgusModel):
    """Output of Agent 2."""

    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=60)
    notes: str = Field(default="", max_length=800)

    @field_validator("evidence")
    @classmethod
    def _unique_evidence_ids(cls, items: list[EvidenceItem]) -> list[EvidenceItem]:
        ids = [e.evidence_id for e in items]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence_id values must be unique")
        return items


# --------------------------------------------------------------------------
# Agent 3 - Risk Specialist
# --------------------------------------------------------------------------


class RiskFinding(ArgusModel):
    """A candidate risk hypothesis, anchored to evidence identifiers."""

    risk_id: Identifier
    title: str = Field(min_length=5, max_length=140)
    category: RiskCategory
    description: str = Field(min_length=40, max_length=1600)
    severity: Severity
    likelihood: Likelihood
    supporting_evidence_ids: list[Identifier] = Field(default_factory=list, max_length=25)
    contradicting_evidence_ids: list[Identifier] = Field(default_factory=list, max_length=25)
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    open_questions: list[str] = Field(default_factory=list, max_length=10)
    mitigating_factors: list[str] = Field(default_factory=list, max_length=10)

    # Deterministically derived downstream; not model-authored.
    evidence_strength: EvidenceStrength = EvidenceStrength.INSUFFICIENT
    strength_rationale: str = ""
    inherent_score: float = Field(default=0.0, ge=0.0, le=25.0)

    @model_validator(mode="after")
    def _no_evidence_overlap(self) -> RiskFinding:
        overlap = set(self.supporting_evidence_ids) & set(self.contradicting_evidence_ids)
        if overlap:
            raise ValueError(
                "evidence cannot both support and contradict the same finding: "
                f"{sorted(overlap)}"
            )
        return self


class RiskAnalysis(ArgusModel):
    """Output of Agent 3."""

    risks: list[RiskFinding] = Field(default_factory=list, max_length=20)
    categories_reviewed_without_finding: list[RiskCategory] = Field(
        default_factory=list,
        max_length=10,
        description=(
            "Categories examined where evidence did not support a finding. "
            "Recorded so silence is distinguishable from omission."
        ),
    )

    @field_validator("risks")
    @classmethod
    def _unique_risk_ids(cls, risks: list[RiskFinding]) -> list[RiskFinding]:
        ids = [r.risk_id for r in risks]
        if len(ids) != len(set(ids)):
            raise ValueError("risk_id values must be unique")
        return risks


# --------------------------------------------------------------------------
# Agent 4 - Policy Analyst
# --------------------------------------------------------------------------

# Expressed as a Literal rather than checked by a validator, so the allowed
# values appear in the JSON Schema the model is shown. A constraint enforced
# only in Python is invisible at generation time: the model cannot honour a rule
# it was never told about, and the first symptom is a retry loop that exhausts
# its budget. Found exactly that way against a live model, where the Challenger
# failed three attempts in a row on a closed vocabulary it had never seen.
TriggerType = Literal["review_trigger", "potential_breach", "informational", "threshold_met"]


class PolicyMatch(ArgusModel):
    """Link between a finding and a clause of the internal policy library."""

    match_id: Identifier
    risk_id: Identifier
    policy_id: Identifier
    clause_reference: str = Field(
        min_length=2,
        max_length=60,
        description="Deterministic citation key, e.g. 'CRF 4.2'.",
    )
    clause_title: str = Field(min_length=3, max_length=200)
    relevance: str = Field(min_length=20, max_length=900)
    trigger_type: TriggerType
    threshold_assessment: str = Field(default="", max_length=600)
    sufficiency_caveat: str = Field(
        default="",
        max_length=600,
        description="Why available evidence may not be sufficient to assert a breach.",
    )


class PolicyAnalysis(ArgusModel):
    """Output of Agent 4."""

    matches: list[PolicyMatch] = Field(default_factory=list, max_length=40)
    unmatched_note: str = Field(default="", max_length=600)

    @field_validator("matches")
    @classmethod
    def _unique_match_ids(cls, matches: list[PolicyMatch]) -> list[PolicyMatch]:
        # Two clauses often come from the same chunk. An agent deriving the id
        # from the chunk therefore produces collisions, which reached
        # persistence as a primary key violation and aborted a completed
        # investigation before this check existed.
        ids = [m.match_id for m in matches]
        if len(ids) != len(set(ids)):
            raise ValueError("match_id values must be unique")
        return matches


# --------------------------------------------------------------------------
# Agent 5 - Challenger / Critic
# --------------------------------------------------------------------------

ChallengeType = Literal[
    "contradictory_evidence",
    "overstated_severity",
    "alternative_explanation",
    "insufficient_evidence",
    "irrelevant_citation",
    "missing_information",
    "correlation_not_causation",
]


class Challenge(ArgusModel):
    """An adversarial argument against a finding, raised by the Challenger."""

    challenge_id: Identifier
    risk_id: Identifier
    challenge_type: ChallengeType
    argument: str = Field(min_length=40, max_length=1600)
    counter_evidence_ids: list[Identifier] = Field(default_factory=list, max_length=15)
    suggested_revision: str = Field(default="", max_length=800)
    proposed_severity: Severity | None = None
    unresolved: bool = Field(
        default=False,
        description="True when the challenge cannot be settled with available evidence.",
    )


class ChallengeReport(ArgusModel):
    """Output of Agent 5."""

    challenges: list[Challenge] = Field(default_factory=list, max_length=30)
    unresolved_contradictions: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("challenges")
    @classmethod
    def _unique_challenge_ids(cls, items: list[Challenge]) -> list[Challenge]:
        ids = [c.challenge_id for c in items]
        if len(ids) != len(set(ids)):
            raise ValueError("challenge_id values must be unique")
        return items


# --------------------------------------------------------------------------
# Agent 6 - Evidence Verifier
# --------------------------------------------------------------------------


class ClaimVerification(ArgusModel):
    """Verdict on whether a finding is actually carried by its citations."""

    verification_id: Identifier
    risk_id: Identifier
    claim: str = Field(min_length=15, max_length=800)
    status: SupportStatus
    reasoning: str = Field(min_length=20, max_length=1200)
    citations_checked: list[Identifier] = Field(default_factory=list, max_length=25)
    irrelevant_citation_ids: list[Identifier] = Field(default_factory=list, max_length=25)
    downgrade_recommended: bool = False


class VerificationReport(ArgusModel):
    """Output of Agent 6."""

    verifications: list[ClaimVerification] = Field(default_factory=list, max_length=30)

    @field_validator("verifications")
    @classmethod
    def _unique_verification_ids(cls, items: list[ClaimVerification]) -> list[ClaimVerification]:
        ids = [v.verification_id for v in items]
        if len(ids) != len(set(ids)):
            raise ValueError("verification_id values must be unique")
        return items


# --------------------------------------------------------------------------
# Agent 7 - Risk Synthesis
# --------------------------------------------------------------------------


class ScoreFactor(ArgusModel):
    """One transparent contributor to the overall provisional rating.

    The overall rating is *not* a label the model emits. It is computed by
    :mod:`ai.scoring.engine` from these factors, so the arithmetic is
    reproducible and unit-testable, and the UI can show the reader exactly
    which factors moved the number.
    """

    key: str = Field(max_length=64)
    label: str = Field(max_length=120)
    detail: str = Field(max_length=600)
    contribution: float = Field(ge=-100.0, le=100.0)
    direction: Literal["increases", "decreases", "neutral"]


class CoverageItem(ArgusModel):
    """Investigation-completeness entry for one expected evidence category."""

    category: RiskCategory
    status: CoverageStatus
    expected: str = Field(max_length=300)
    found_evidence_ids: list[Identifier] = Field(default_factory=list, max_length=25)
    note: str = Field(default="", max_length=400)


class MindChanger(ArgusModel):
    """What would change my mind - the habit that separates analysts from tools."""

    risk_id: Identifier
    would_increase: str = Field(
        default="",
        max_length=600,
        description="Evidence that would raise the assessment.",
    )
    would_decrease: str = Field(
        default="",
        max_length=600,
        description="Evidence that would lower the assessment.",
    )


class SynthesisNarrative(ArgusModel):
    """The only free-text portion of synthesis the model is trusted to write."""

    executive_summary: str = Field(min_length=80, max_length=2500)
    key_judgements: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    recommended_followup: list[str] = Field(default_factory=list, max_length=10)
    mind_changers: list[MindChanger] = Field(default_factory=list, max_length=20)


class RiskAssessment(ArgusModel):
    """Provisional assessment presented to the human reviewer.

    ``overall_level`` and ``overall_score`` come from the deterministic scoring
    engine. ``narrative`` comes from the model. Keeping the two apart is what
    lets ARGUS claim the rating is explainable rather than merely asserted.
    """

    overall_level: RiskLevel
    overall_score: float = Field(ge=0.0, le=100.0)
    score_factors: list[ScoreFactor] = Field(default_factory=list)
    category_levels: dict[str, RiskLevel] = Field(default_factory=dict)
    evidence_strength: EvidenceStrength = EvidenceStrength.INSUFFICIENT
    coverage: list[CoverageItem] = Field(default_factory=list)
    narrative: SynthesisNarrative
    generated_at: datetime = Field(default_factory=_utcnow)


# --------------------------------------------------------------------------
# Ask ARGUS - grounded question answering
# --------------------------------------------------------------------------


class AnswerCitation(ArgusModel):
    evidence_id: Identifier
    document_name: str = Field(max_length=200)
    section_reference: str = Field(max_length=120)
    quote: str = Field(max_length=800)


class GroundedAnswer(ArgusModel):
    """Output of the Ask ARGUS capability. Refuses rather than speculates."""

    answer: str = Field(min_length=1, max_length=3000)
    citations: list[AnswerCitation] = Field(default_factory=list, max_length=15)
    answerable: bool = True
    insufficient_evidence_note: str = Field(default="", max_length=600)

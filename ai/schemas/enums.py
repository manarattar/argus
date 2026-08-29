"""Controlled vocabularies for the ARGUS domain.

Every enum here is part of the system's public contract: it appears in stored
records, API payloads, evaluation datasets and the UI. Values are stable
lowercase slugs so they survive serialisation; ``label`` carries the
human-facing string so the frontend never has to re-implement presentation
rules that belong to the domain.
"""

from __future__ import annotations

from enum import Enum


class _LabelledEnum(str, Enum):
    """String enum with a display label derived from the member name."""

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


class RiskCategory(_LabelledEnum):
    """Risk taxonomy for counterparty review.

    The taxonomy is intentionally domain configuration rather than a hardcoded
    constant: :class:`argus_api.domain.DomainConfig` selects the subset that a
    given review type may use.
    """

    FINANCIAL = "financial"
    OPERATIONAL = "operational"
    GOVERNANCE = "governance"
    COMPLIANCE = "compliance"
    LEGAL = "legal"
    REPUTATIONAL = "reputational"
    CYBER_TECHNOLOGY = "cyber_technology"
    ESG_SUSTAINABILITY = "esg_sustainability"
    CONCENTRATION = "concentration"
    SUPPLY_CHAIN = "supply_chain"

    @property
    def label(self) -> str:
        overrides = {
            "cyber_technology": "Cyber & Technology",
            "esg_sustainability": "ESG & Sustainability",
        }
        return overrides.get(self.value, self.name.replace("_", " ").title())


class Severity(_LabelledEnum):
    """How damaging the risk would be if it materialised."""

    NEGLIGIBLE = "negligible"
    MINOR = "minor"
    MODERATE = "moderate"
    MAJOR = "major"
    SEVERE = "severe"

    @property
    def ordinal(self) -> int:
        return _SEVERITY_ORDER[self]


_SEVERITY_ORDER = {
    Severity.NEGLIGIBLE: 1,
    Severity.MINOR: 2,
    Severity.MODERATE: 3,
    Severity.MAJOR: 4,
    Severity.SEVERE: 5,
}


class Likelihood(_LabelledEnum):
    """How probable the risk is over the review horizon."""

    RARE = "rare"
    UNLIKELY = "unlikely"
    POSSIBLE = "possible"
    LIKELY = "likely"
    ALMOST_CERTAIN = "almost_certain"

    @property
    def ordinal(self) -> int:
        return _LIKELIHOOD_ORDER[self]


_LIKELIHOOD_ORDER = {
    Likelihood.RARE: 1,
    Likelihood.UNLIKELY: 2,
    Likelihood.POSSIBLE: 3,
    Likelihood.LIKELY: 4,
    Likelihood.ALMOST_CERTAIN: 5,
}


class RiskLevel(_LabelledEnum):
    """Overall provisional rating produced by the scoring engine."""

    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    HIGH = "high"

    @property
    def ordinal(self) -> int:
        return _RISK_LEVEL_ORDER[self]

    @classmethod
    def from_ordinal(cls, value: int) -> RiskLevel:
        for level, ordinal in _RISK_LEVEL_ORDER.items():
            if ordinal == value:
                return level
        raise ValueError(f"No risk level with ordinal {value}")


_RISK_LEVEL_ORDER = {
    RiskLevel.LOW: 1,
    RiskLevel.MODERATE: 2,
    RiskLevel.ELEVATED: 3,
    RiskLevel.HIGH: 4,
}


class EvidenceStrength(_LabelledEnum):
    """Interpretable stand-in for a confidence percentage.

    ARGUS deliberately avoids surfacing pseudo-precise probabilities such as
    "97% confident". This band is computed by
    :mod:`ai.scoring.uncertainty` from observable signals (coverage,
    independent sources, contradictions, verifier status).
    """

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"

    @property
    def label(self) -> str:
        return f"{self.name.title()} Evidence"

    @property
    def ordinal(self) -> int:
        return {"strong": 4, "moderate": 3, "weak": 2, "insufficient": 1}[self.value]


class SupportStatus(_LabelledEnum):
    """Verifier verdict for a single material claim."""

    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONFLICTING = "conflicting"

    @property
    def label(self) -> str:
        overrides = {"conflicting": "Conflicting Evidence"}
        return overrides.get(self.value, self.name.replace("_", " ").title())


class EvidenceKind(_LabelledEnum):
    """Separates observable facts from the model's reading of them.

    Conflating the two is the most common failure mode in LLM analysis
    pipelines, so the distinction is enforced in the schema rather than left
    to prose.
    """

    FACT = "fact"
    INTERPRETATION = "interpretation"


class CoverageStatus(_LabelledEnum):
    """Investigation completeness for an expected evidence category."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


class CaseStatus(_LabelledEnum):
    DRAFT = "draft"
    INVESTIGATING = "investigating"
    AWAITING_REVIEW = "awaiting_review"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class InvestigationStatus(_LabelledEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_HUMAN_REVIEW = "awaiting_human_review"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(_LabelledEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRIED = "retried"
    SKIPPED = "skipped"


class ReviewDecision(_LabelledEnum):
    APPROVE = "approve"
    MODIFY = "modify"
    REJECT = "reject"
    REQUEST_DEEPER_INVESTIGATION = "request_deeper_investigation"
    ESCALATE = "escalate"
    MARK_FALSE_POSITIVE = "mark_false_positive"


class ActorType(_LabelledEnum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"

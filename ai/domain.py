"""Domain configuration: what makes ARGUS a platform rather than one app.

The agents, retrieval, grounding, scoring, review workflow and evaluation
harness contain no counterparty-review logic. Everything specific to a review
type - which risk categories are in scope, which evidence a complete file
contains, which policy library applies, which thresholds trigger escalation -
lives in a :class:`DomainConfig` value.

Adding "Vendor Risk" is therefore a configuration exercise plus a policy
library, not a fork of the pipeline. That claim is only credible if the
extension points are visible, so the registry below deliberately carries
*declared but unimplemented* domains marked ``status="design"``. The API
exposes them, the Architecture page renders them, and nothing pretends they are
finished: only ``counterparty_review`` has a corpus and recordings behind it.

Honesty note: the three design-stage domains are scoped, not built. They are
included to show the seam, and the UI labels them as such.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ai.schemas.enums import RiskCategory

DomainStatus = Literal["implemented", "design"]


@dataclass(frozen=True)
class ExpectedEvidence:
    """One evidence category a complete file for this domain should contain.

    Drives the Investigation Completeness panel: coverage is measured against
    what the domain says a good file looks like, not against whatever the model
    happened to find - otherwise "complete" would only ever mean "the model
    stopped".
    """

    key: str
    category: RiskCategory
    label: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class EscalationRule:
    """A deterministic condition that forces human escalation.

    Expressed as data rather than prompt text because escalation is a control,
    and controls should not depend on a model choosing to honour them.
    """

    key: str
    label: str
    description: str


@dataclass(frozen=True)
class DomainConfig:
    """Everything that varies between review types."""

    key: str
    name: str
    subject_noun: str
    description: str
    status: DomainStatus
    risk_categories: tuple[RiskCategory, ...]
    policy_library: tuple[str, ...]
    expected_evidence: tuple[ExpectedEvidence, ...] = field(default_factory=tuple)
    escalation_rules: tuple[EscalationRule, ...] = field(default_factory=tuple)
    review_objective: str = ""

    @property
    def implemented(self) -> bool:
        return self.status == "implemented"

    def category_in_scope(self, category: RiskCategory) -> bool:
        return category in self.risk_categories


COUNTERPARTY_REVIEW = DomainConfig(
    key="counterparty_review",
    name="Counterparty Risk Review",
    subject_noun="counterparty",
    description=(
        "Periodic review of a corporate counterparty's financial resilience, "
        "governance, operational dependencies and technology risk, against the "
        "internal counterparty risk framework."
    ),
    status="implemented",
    review_objective=(
        "Determine whether the counterparty's risk profile remains within "
        "appetite, identify material changes since the previous review, and "
        "surface anything requiring escalation or additional evidence."
    ),
    risk_categories=(
        RiskCategory.FINANCIAL,
        RiskCategory.GOVERNANCE,
        RiskCategory.OPERATIONAL,
        RiskCategory.CONCENTRATION,
        RiskCategory.SUPPLY_CHAIN,
        RiskCategory.CYBER_TECHNOLOGY,
        RiskCategory.COMPLIANCE,
        RiskCategory.LEGAL,
        RiskCategory.REPUTATIONAL,
        RiskCategory.ESG_SUSTAINABILITY,
    ),
    policy_library=(
        "counterparty-risk-framework",
        "financial-resilience-standard",
        "governance-oversight-standard",
        "technology-risk-assessment-standard",
    ),
    expected_evidence=(
        ExpectedEvidence(
            key="financial_position",
            category=RiskCategory.FINANCIAL,
            label="Financial position and trend",
            description=(
                "Revenue, margin, leverage and liquidity across at least two " "comparable periods."
            ),
        ),
        ExpectedEvidence(
            key="revenue_concentration",
            category=RiskCategory.CONCENTRATION,
            label="Revenue concentration",
            description="Share of revenue attributable to the largest customers.",
        ),
        ExpectedEvidence(
            key="governance_structure",
            category=RiskCategory.GOVERNANCE,
            label="Board and governance arrangements",
            description=(
                "Board composition, independence, audit committee activity and "
                "any auditor findings."
            ),
        ),
        ExpectedEvidence(
            key="operational_dependencies",
            category=RiskCategory.SUPPLY_CHAIN,
            label="Supplier and operational dependencies",
            description="Single-source suppliers and concentration in the supply base.",
        ),
        ExpectedEvidence(
            key="technology_controls",
            category=RiskCategory.CYBER_TECHNOLOGY,
            label="Technology and cyber controls",
            description=(
                "Control maturity, incidents, remediation status and independent "
                "assessment where available."
            ),
        ),
        ExpectedEvidence(
            key="legal_and_compliance",
            category=RiskCategory.LEGAL,
            label="Legal and regulatory matters",
            description="Litigation, regulatory findings and material contingencies.",
            required=False,
        ),
    ),
    escalation_rules=(
        EscalationRule(
            key="high_overall",
            label="Overall rating of High",
            description=(
                "Any provisional rating of High is escalated to a senior reviewer "
                "before the assessment can be approved."
            ),
        ),
        EscalationRule(
            key="potential_breach",
            label="Potential policy breach identified",
            description=(
                "A finding matched to a policy clause as a potential breach requires "
                "senior sign-off regardless of the overall rating."
            ),
        ),
        EscalationRule(
            key="insufficient_evidence_material_risk",
            label="Material risk on insufficient evidence",
            description=(
                "A Major or Severe finding whose evidence band is Weak or "
                "Insufficient must be escalated rather than approved, because the "
                "gap - not the rating - is the decision-relevant fact."
            ),
        ),
    ),
)


# Declared extension points. Scoped only - see the module docstring.
_DESIGN_DOMAINS: tuple[DomainConfig, ...] = (
    DomainConfig(
        key="kyc_onboarding",
        name="KYC / Onboarding Review",
        subject_noun="applicant",
        description=(
            "Identity, ownership and sanctions review at onboarding. Reuses "
            "ingestion, retrieval, verification, review and audit unchanged; "
            "needs a beneficial-ownership schema and a sanctions-screening tool."
        ),
        status="design",
        risk_categories=(
            RiskCategory.COMPLIANCE,
            RiskCategory.LEGAL,
            RiskCategory.REPUTATIONAL,
            RiskCategory.GOVERNANCE,
        ),
        policy_library=("kyc-standard",),
    ),
    DomainConfig(
        key="vendor_risk",
        name="Third-Party / Vendor Risk",
        subject_noun="vendor",
        description=(
            "Assessment of an outsourcing or technology vendor. Closest to the "
            "implemented domain: the same categories with different thresholds "
            "and a service-continuity evidence set."
        ),
        status="design",
        risk_categories=(
            RiskCategory.OPERATIONAL,
            RiskCategory.CYBER_TECHNOLOGY,
            RiskCategory.SUPPLY_CHAIN,
            RiskCategory.COMPLIANCE,
            RiskCategory.CONCENTRATION,
        ),
        policy_library=("technology-risk-assessment-standard",),
    ),
    DomainConfig(
        key="compliance_review",
        name="Regulatory Compliance Review",
        subject_noun="business unit",
        description=(
            "Internal review against a regulatory obligation. The Challenger and "
            "Verifier carry over directly; the policy layer would point at an "
            "obligations register rather than an internal framework."
        ),
        status="design",
        risk_categories=(
            RiskCategory.COMPLIANCE,
            RiskCategory.LEGAL,
            RiskCategory.GOVERNANCE,
            RiskCategory.REPUTATIONAL,
        ),
        policy_library=("obligations-register",),
    ),
)


DOMAIN_REGISTRY: dict[str, DomainConfig] = {
    domain.key: domain for domain in (COUNTERPARTY_REVIEW, *_DESIGN_DOMAINS)
}

DEFAULT_DOMAIN = COUNTERPARTY_REVIEW.key


def get_domain(key: str | None = None) -> DomainConfig:
    """Look up a domain configuration, defaulting to the implemented one."""
    if not key:
        return COUNTERPARTY_REVIEW
    try:
        return DOMAIN_REGISTRY[key]
    except KeyError as exc:
        known = ", ".join(sorted(DOMAIN_REGISTRY))
        raise ValueError(f"Unknown domain {key!r}. Known domains: {known}") from exc


def list_domains() -> list[DomainConfig]:
    """All registered domains, implemented ones first."""
    return sorted(DOMAIN_REGISTRY.values(), key=lambda d: (d.status != "implemented", d.name))

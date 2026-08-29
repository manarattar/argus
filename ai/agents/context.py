"""Shared execution context and payload rendering for agents.

Every agent is a plain function taking an :class:`AgentContext` and returning a
validated model. There is no agent base class and no message-passing framework:
the orchestration is the graph's job, and keeping the agents as functions makes
each one directly callable from a test or an evaluation case without standing
anything up.

The rendering helpers matter more than they look. They are the only place case
content is turned into prompt text, so the trust boundary from
:mod:`ai.prompts.library` is applied in exactly one place rather than being
re-implemented, slightly differently, in each agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ai.domain import DomainConfig
from ai.prompts.library import wrap_untrusted
from ai.providers.base import LLMProvider
from ai.retrieval.search import HybridIndex, SearchHit
from ai.schemas.models import Challenge, ClaimVerification, EvidenceItem, PolicyMatch, RiskFinding


@dataclass
class AgentContext:
    """Everything an agent needs, injected rather than imported."""

    provider: LLMProvider
    index: HybridIndex
    domain: DomainConfig
    case_summary: str
    max_attempts: int = 3
    max_tokens: int = 4096
    temperature: float = 0.0
    #: Populated as the graph runs, so later agents can see retrieval quality.
    metrics: dict[str, Any] = field(default_factory=dict)

    def chunk_texts(self, doc_kind: str | None = "case") -> dict[str, str]:
        """Stored chunk text, keyed by id - the ground truth for verification."""
        return {
            c.chunk_id: c.text
            for c in self.index.chunks
            if doc_kind is None or c.doc_kind == doc_kind
        }


def render_hits(hits: list[SearchHit], *, label: str = "document") -> str:
    """Render retrieved chunks as untrusted, citable blocks.

    Each block carries the exact ``chunk_id``, ``document_id`` and
    ``section_reference`` the agent must copy into its citations. Supplying them
    explicitly is what turns citation into transcription rather than recall.
    """
    if not hits:
        return "(no sections retrieved)"

    blocks: list[str] = []
    for hit in hits:
        chunk = hit.chunk
        header = "\n".join(
            [
                f"chunk_id: {chunk.chunk_id}",
                f"document_id: {chunk.document_id}",
                f"document_name: {chunk.document_name}",
                f"section_reference: {chunk.citation_key}",
                f"retrieved_by: {hit.retrieved_by}",
            ]
        )
        blocks.append(
            wrap_untrusted(label, f"{header}\n---\n{chunk.text}", identifier=chunk.chunk_id)
        )
    return "\n\n".join(blocks)


def render_evidence(items: list[EvidenceItem], *, include_quotes: bool = True) -> str:
    """Compact evidence digest for downstream agents.

    Quotes are included so later agents can judge whether a citation actually
    carries a claim, but the whole set is wrapped as untrusted content because
    the quotes are still counterparty text.
    """
    if not items:
        return "(no evidence extracted)"

    lines: list[str] = []
    for item in items:
        lines.append(
            f"[{item.evidence_id}] ({item.category.value} / {item.kind.value}, "
            f"materiality={item.materiality.value}) {item.statement}"
        )
        lines.append(f"    source: {item.document_name}, {item.section_reference}")
        if include_quotes:
            lines.append(f'    quote: "{item.quote}"')
    return wrap_untrusted("retrieved_evidence", "\n".join(lines))


def render_risks(risks: list[RiskFinding], *, include_description: bool = True) -> str:
    """Findings digest, used by the policy, challenger and verifier agents."""
    if not risks:
        return "(no findings)"

    blocks: list[str] = []
    for risk in risks:
        parts = [
            f"[{risk.risk_id}] {risk.title}",
            f"  category: {risk.category.value}",
            f"  severity: {risk.severity.value} | likelihood: {risk.likelihood.value}",
            f"  supporting_evidence_ids: {', '.join(risk.supporting_evidence_ids) or 'none'}",
            (
                "  contradicting_evidence_ids: "
                f"{', '.join(risk.contradicting_evidence_ids) or 'none'}"
            ),
        ]
        if include_description:
            parts.append(f"  description: {risk.description}")
        if risk.assumptions:
            parts.append(f"  assumptions: {'; '.join(risk.assumptions)}")
        if risk.mitigating_factors:
            parts.append(f"  mitigating_factors: {'; '.join(risk.mitigating_factors)}")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def render_policy_matches(matches: list[PolicyMatch]) -> str:
    if not matches:
        return "(no policy clauses matched)"
    return "\n".join(
        f"[{m.match_id}] risk={m.risk_id} clause={m.clause_reference} "
        f"({m.trigger_type}) - {m.clause_title}: {m.relevance}"
        for m in matches
    )


def render_challenges(challenges: list[Challenge]) -> str:
    if not challenges:
        return "(no challenges raised)"
    return "\n".join(
        f"[{c.challenge_id}] risk={c.risk_id} type={c.challenge_type} "
        f"unresolved={c.unresolved} - {c.argument}"
        for c in challenges
    )


def render_verifications(verifications: list[ClaimVerification]) -> str:
    if not verifications:
        return "(no verification performed)"
    return "\n".join(
        f"[{v.verification_id}] risk={v.risk_id} status={v.status.value} "
        f"downgrade_recommended={v.downgrade_recommended} - {v.reasoning}"
        for v in verifications
    )


def render_categories(domain: DomainConfig) -> str:
    """The category vocabulary in scope for this domain."""
    return "\n".join(f"- {c.value}: {c.label}" for c in domain.risk_categories)

"""Evidence graph construction.

The lineage the graph draws - rating to finding to evidence to document section
to policy clause - is not reconstructed by inspecting text. It is a join over
tables that already hold those relationships, because the pipeline stored
citations as identifiers rather than prose.

Node and edge shapes are kept deliberately small: the frontend renders the
layout, so the API sends structure, not presentation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus_api.db.models import ChallengeRow, Evidence, Investigation, PolicyMatchRow, Risk

# Relationship vocabulary rendered by the graph legend.
SUPPORTS = "supports"
CONTRADICTS = "contradicts"
DERIVED_FROM = "derived_from"
TRIGGERS = "triggers"
CHALLENGES = "challenges"
ROLLS_UP_TO = "rolls_up_to"


@dataclass
class GraphNode:
    id: str
    kind: str
    label: str
    sublabel: str = ""
    weight: float = 1.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str
    weight: float = 1.0


@dataclass
class EvidenceGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "counts": {
                kind: sum(1 for n in self.nodes if n.kind == kind)
                for kind in {n.kind for n in self.nodes}
            },
        }


def build_evidence_graph(session: Session, investigation: Investigation) -> EvidenceGraph:
    """Assemble the full lineage graph for one investigation."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    seen: set[str] = set()

    def add_node(node: GraphNode) -> None:
        if node.id not in seen:
            seen.add(node.id)
            nodes.append(node)

    # -- assessment root ---------------------------------------------------
    assessment_id = "assessment"
    add_node(
        GraphNode(
            id=assessment_id,
            kind="assessment",
            label=f"{(investigation.overall_level or 'unrated').title()} risk",
            sublabel=f"{investigation.overall_score:.0f}/100",
            weight=3.0,
            meta={
                "level": investigation.overall_level,
                "score": investigation.overall_score,
                "evidence_strength": investigation.evidence_strength,
            },
        )
    )

    # -- documents ---------------------------------------------------------
    evidence_rows = (
        session.execute(select(Evidence).where(Evidence.investigation_id == investigation.id))
        .scalars()
        .all()
    )
    for row in evidence_rows:
        document_node = f"doc:{row.document_id}"
        add_node(
            GraphNode(
                id=document_node,
                kind="document",
                label=row.document_name,
                sublabel="Source document",
                weight=1.6,
                meta={"document_id": row.document_id},
            )
        )

    # -- evidence ----------------------------------------------------------
    for row in evidence_rows:
        node_id = f"ev:{row.evidence_id}"
        add_node(
            GraphNode(
                id=node_id,
                kind="evidence",
                label=row.evidence_id,
                sublabel=row.statement[:120],
                weight=1.0,
                meta={
                    "statement": row.statement,
                    "quote": row.quote,
                    "kind": row.kind,
                    "category": row.category,
                    "document_name": row.document_name,
                    "section_reference": row.section_reference,
                    "grounding_score": row.grounding_score,
                },
            )
        )
        edges.append(
            GraphEdge(source=node_id, target=f"doc:{row.document_id}", relation=DERIVED_FROM)
        )

    # -- findings ----------------------------------------------------------
    risk_rows = (
        session.execute(select(Risk).where(Risk.investigation_id == investigation.id))
        .scalars()
        .all()
    )
    for risk in risk_rows:
        node_id = f"risk:{risk.risk_id}"
        add_node(
            GraphNode(
                id=node_id,
                kind="risk",
                label=risk.title,
                sublabel=f"{risk.category.replace('_', ' ').title()} - {risk.severity}",
                weight=2.2,
                meta={
                    "risk_id": risk.risk_id,
                    "category": risk.category,
                    "severity": risk.severity,
                    "likelihood": risk.likelihood,
                    "evidence_strength": risk.evidence_strength,
                    "adjusted_score": risk.adjusted_score,
                    "is_false_positive": risk.is_false_positive,
                },
            )
        )
        edges.append(
            GraphEdge(
                source=node_id,
                target=assessment_id,
                relation=ROLLS_UP_TO,
                weight=max(risk.adjusted_score, 0.5),
            )
        )
        for evidence_id in risk.supporting_evidence_ids:
            edges.append(GraphEdge(source=f"ev:{evidence_id}", target=node_id, relation=SUPPORTS))
        for evidence_id in risk.contradicting_evidence_ids:
            edges.append(
                GraphEdge(source=f"ev:{evidence_id}", target=node_id, relation=CONTRADICTS)
            )

    # -- policy clauses ----------------------------------------------------
    policy_rows = (
        session.execute(
            select(PolicyMatchRow).where(PolicyMatchRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    for match in policy_rows:
        node_id = f"policy:{match.clause_reference}"
        add_node(
            GraphNode(
                id=node_id,
                kind="policy",
                label=match.clause_reference,
                sublabel=match.clause_title,
                weight=1.4,
                meta={
                    "clause_reference": match.clause_reference,
                    "clause_title": match.clause_title,
                    "trigger_type": match.trigger_type,
                    "relevance": match.relevance,
                    "threshold_assessment": match.threshold_assessment,
                },
            )
        )
        edges.append(
            GraphEdge(
                source=f"risk:{match.risk_id}",
                target=node_id,
                relation=TRIGGERS,
                weight=1.5 if match.trigger_type != "informational" else 0.8,
            )
        )

    # -- challenges --------------------------------------------------------
    challenge_rows = (
        session.execute(
            select(ChallengeRow).where(ChallengeRow.investigation_id == investigation.id)
        )
        .scalars()
        .all()
    )
    for challenge in challenge_rows:
        node_id = f"challenge:{challenge.challenge_id}"
        add_node(
            GraphNode(
                id=node_id,
                kind="challenge",
                label=challenge.challenge_type.replace("_", " ").title(),
                sublabel=challenge.argument[:120],
                weight=1.2,
                meta={
                    "challenge_id": challenge.challenge_id,
                    "challenge_type": challenge.challenge_type,
                    "argument": challenge.argument,
                    "unresolved": challenge.unresolved,
                    "suggested_revision": challenge.suggested_revision,
                },
            )
        )
        edges.append(
            GraphEdge(source=node_id, target=f"risk:{challenge.risk_id}", relation=CHALLENGES)
        )
        for evidence_id in challenge.counter_evidence_ids:
            edges.append(GraphEdge(source=f"ev:{evidence_id}", target=node_id, relation=SUPPORTS))

    # Drop edges whose endpoints were filtered out, so the client never has to
    # defend against dangling references.
    valid = {n.id for n in nodes}
    edges = [e for e in edges if e.source in valid and e.target in valid]

    return EvidenceGraph(nodes=nodes, edges=edges)


def lineage_for_risk(graph: EvidenceGraph, risk_id: str) -> dict[str, list[str]]:
    """Node ids reachable from one finding, for click-to-highlight in the UI."""
    target = f"risk:{risk_id}"
    supporting = [e.source for e in graph.edges if e.target == target and e.relation == SUPPORTS]
    contradicting = [
        e.source for e in graph.edges if e.target == target and e.relation == CONTRADICTS
    ]
    documents = [
        e.target
        for e in graph.edges
        if e.relation == DERIVED_FROM and e.source in set(supporting + contradicting)
    ]
    policies = [e.target for e in graph.edges if e.source == target and e.relation == TRIGGERS]
    challenges = [e.source for e in graph.edges if e.target == target and e.relation == CHALLENGES]
    return {
        "risk": [target],
        "supporting_evidence": supporting,
        "contradicting_evidence": contradicting,
        "documents": sorted(set(documents)),
        "policies": policies,
        "challenges": challenges,
    }

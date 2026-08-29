"""The seven investigation agents.

Each is a function from :class:`~ai.agents.context.AgentContext` plus its inputs
to a validated schema object. They share the same shape deliberately: no agent
holds state, none calls another, and none decides what runs next. Sequencing,
retries and error handling belong to the graph
(:mod:`ai.graphs.investigation`), which keeps each agent small enough to read in
one sitting and testable in isolation.

Note what the agents do *not* do. None of them assigns the overall rating, and
none decides its own confidence. Both are computed from their outputs by
:mod:`ai.scoring`. The agents supply judgement; the system supplies arithmetic.
"""

from __future__ import annotations

from ai.agents.context import (
    AgentContext,
    render_categories,
    render_challenges,
    render_evidence,
    render_hits,
    render_policy_matches,
    render_risks,
    render_verifications,
)
from ai.prompts.library import (
    CHALLENGER,
    EVIDENCE_EXTRACTOR,
    PLANNER,
    POLICY_ANALYST,
    RISK_SPECIALIST,
    SYNTHESISER,
    VERIFIER,
    Prompt,
)
from ai.providers.structured import ModelT, StructuredResult, generate_structured
from ai.retrieval.search import SearchHit
from ai.schemas.enums import RiskCategory
from ai.schemas.models import (
    Challenge,
    ChallengeReport,
    ClaimVerification,
    EvidenceExtraction,
    EvidenceItem,
    InvestigationPlan,
    PolicyAnalysis,
    PolicyMatch,
    RiskAnalysis,
    RiskAssessment,
    RiskFinding,
    SynthesisNarrative,
    VerificationReport,
)

# How many chunks each retrieval-backed agent pulls. Sized so the prompt stays
# well inside context while covering the corpus for a review of this shape.
EVIDENCE_TOP_K = 9
POLICY_TOP_K = 4


def _run(
    ctx: AgentContext,
    prompt: Prompt,
    schema: type[ModelT],
    user: str,
    purpose: str,
) -> StructuredResult[ModelT]:
    """Single entry point so every agent gets identical retry and accounting."""
    return generate_structured(
        ctx.provider,
        schema,
        system=prompt.system,
        user=user,
        purpose=purpose,
        max_attempts=ctx.max_attempts,
        max_tokens=ctx.max_tokens,
        temperature=ctx.temperature,
    )


# ---------------------------------------------------------------------------
# Agent 1 - Intake & Planning
# ---------------------------------------------------------------------------


def plan_investigation(ctx: AgentContext) -> StructuredResult[InvestigationPlan]:
    """Read the case and decide what the investigation needs to establish."""
    inventory = "\n".join(
        f"- {c.document_name} (document_id: {c.document_id})"
        for c in {c.document_id: c for c in ctx.index.chunks if c.doc_kind == "case"}.values()
    )
    expected = "\n".join(
        f"- {e.label} ({'required' if e.required else 'optional'}): {e.description}"
        for e in ctx.domain.expected_evidence
    )

    user = f"""\
## Case
{ctx.case_summary}

## Review type
{ctx.domain.name} - {ctx.domain.description}

Objective for this review type:
{ctx.domain.review_objective}

## Risk categories in scope
{render_categories(ctx.domain)}

## Evidence a complete file for this review type contains
{expected}

## Documents actually available in this case
{inventory or '(none)'}

Produce the investigation plan. Compare the available documents against the
expected evidence above and record every material gap."""

    return _run(ctx, PLANNER, InvestigationPlan, user, "plan")


# ---------------------------------------------------------------------------
# Agent 2 - Evidence Extraction
# ---------------------------------------------------------------------------


def extract_evidence(
    ctx: AgentContext, plan: InvestigationPlan
) -> tuple[StructuredResult[EvidenceExtraction], float]:
    """Retrieve material sections and lift citable evidence from them.

    Retrieval is driven by the plan's priority categories rather than one broad
    query, so each category gets its own targeted pass. Returns the extraction
    together with the mean retrieval quality, which feeds the uncertainty model.
    """
    seen: dict[str, SearchHit] = {}
    qualities: list[float] = []

    # Retrieve for the planner's priorities *and* for every category the domain
    # says a complete file must evidence. The planner orders the work; it does
    # not get to narrow it. Without this, a category the planner overlooked is
    # never searched, and the resulting coverage gap is indistinguishable from
    # the document genuinely not containing it - which is the more alarming of
    # the two readings and the wrong one.
    required = [e.category for e in ctx.domain.expected_evidence if e.required]
    categories: list[RiskCategory] = list(dict.fromkeys([*plan.priority_categories, *required]))

    for category in categories:
        expected = [e for e in ctx.domain.expected_evidence if e.category == category]
        terms = " ".join(e.description for e in expected) or category.label
        query = f"{category.label} {terms}"
        response = ctx.index.search(query, top_k=EVIDENCE_TOP_K, doc_kind="case")
        qualities.append(response.quality)
        for hit in response.hits:
            seen.setdefault(hit.chunk.chunk_id, hit)

    hits = list(seen.values())
    retrieval_quality = round(sum(qualities) / len(qualities), 3) if qualities else 0.0
    ctx.metrics["retrieval_quality"] = retrieval_quality
    ctx.metrics["chunks_retrieved"] = len(hits)

    user = f"""\
## Case
{ctx.case_summary}

## Investigation objective
{plan.objective}

## Priority categories
{', '.join(c.value for c in categories)}

## Retrieved document sections
{render_hits(hits)}

Extract the material evidence. Copy `chunk_id`, `document_id`, `document_name`
and `section_reference` exactly as given in each block. Every quote must be
verbatim text from the block you cite.

Cover every priority category listed above that the sections actually speak to -
a category left with no evidence is reported to the analyst as a gap in the
file, so leaving one out because you did not look is misleading.

For each category, extract the evidence that cuts both ways. Buffer stock
against a supply dependency, covenant headroom against rising leverage, closed
findings against a control weakness: these are as material as the exposures
themselves, and an extraction containing only adverse statements is a sign of
biased reading rather than of a risky subject."""

    result = _run(ctx, EVIDENCE_EXTRACTOR, EvidenceExtraction, user, "evidence")
    return result, retrieval_quality


# ---------------------------------------------------------------------------
# Agent 3 - Risk Specialist
# ---------------------------------------------------------------------------


def analyse_risks(
    ctx: AgentContext, plan: InvestigationPlan, evidence: list[EvidenceItem]
) -> StructuredResult[RiskAnalysis]:
    """Turn grounded evidence into calibrated, citation-anchored findings."""
    gaps = "\n".join(
        f"- {gap.description} (matters because: {gap.why_it_matters})"
        for gap in plan.information_gaps
    )

    user = f"""\
## Case
{ctx.case_summary}

## Investigation objective
{plan.objective}

## Risk categories in scope
{render_categories(ctx.domain)}

## Known information gaps
{gaps or '(none recorded)'}

## Grounded evidence
Every item below was verified against its source document. You may cite these
ids and no others.

{render_evidence(evidence)}

Identify the risks this evidence supports. Cite supporting and contradicting
evidence ids for each. Where a category was considered but the evidence does not
support a finding, record it in `categories_reviewed_without_finding`."""

    return _run(ctx, RISK_SPECIALIST, RiskAnalysis, user, "risk")


# ---------------------------------------------------------------------------
# Agent 4 - Policy Analyst
# ---------------------------------------------------------------------------


def analyse_policy(
    ctx: AgentContext, risks: list[RiskFinding], evidence: list[EvidenceItem]
) -> StructuredResult[PolicyAnalysis]:
    """Retrieve the policy clauses that bear on each finding and classify them."""
    seen: dict[str, SearchHit] = {}
    for risk in risks:
        query = f"{risk.title} {risk.category.label} {risk.description[:280]}"
        response = ctx.index.search(query, top_k=POLICY_TOP_K, doc_kind="policy")
        for hit in response.hits:
            seen.setdefault(hit.chunk.chunk_id, hit)

    policy_hits = list(seen.values())
    ctx.metrics["policy_chunks_retrieved"] = len(policy_hits)

    user = f"""\
## Case
{ctx.case_summary}

## Findings to assess against policy
{render_risks(risks)}

## Supporting evidence
{render_evidence(evidence, include_quotes=False)}

## Retrieved policy clauses
{render_hits(policy_hits)}

Match findings to the clauses that genuinely bear on them. Use the clause
reference exactly as it appears in the retrieved text. Where a numeric threshold
is involved, state both the policy figure and the observed figure."""

    return _run(ctx, POLICY_ANALYST, PolicyAnalysis, user, "policy")


# ---------------------------------------------------------------------------
# Agent 5 - Challenger
# ---------------------------------------------------------------------------


def challenge_findings(
    ctx: AgentContext, risks: list[RiskFinding], evidence: list[EvidenceItem]
) -> StructuredResult[ChallengeReport]:
    """Argue against the findings using only the evidence on file."""
    user = f"""\
## Case
{ctx.case_summary}

## Findings to challenge
{render_risks(risks)}

## Complete evidence set
This is everything on file, including evidence the risk analysis did not cite.
Evidence it overlooked is often the strongest basis for a challenge.

{render_evidence(evidence)}

Challenge these findings. For each challenge, name the type, make the argument,
cite counter-evidence ids where they exist, and propose a concrete revision.
Mark a challenge unresolved when the file cannot settle it either way."""

    return _run(ctx, CHALLENGER, ChallengeReport, user, "challenge")


# ---------------------------------------------------------------------------
# Agent 6 - Evidence Verifier
# ---------------------------------------------------------------------------


def verify_claims(
    ctx: AgentContext, risks: list[RiskFinding], evidence: list[EvidenceItem]
) -> StructuredResult[VerificationReport]:
    """Check whether each finding's citations actually carry its claim."""
    user = f"""\
## Findings to verify
{render_risks(risks)}

## Evidence available for checking
{render_evidence(evidence)}

For each finding, state the claim being checked, decide whether the cited
evidence establishes it, and name any citation that does not in fact bear on the
claim. Produce one verification per finding."""

    return _run(ctx, VERIFIER, VerificationReport, user, "verify")


# ---------------------------------------------------------------------------
# Agent 7 - Risk Synthesis
# ---------------------------------------------------------------------------


def synthesise_narrative(
    ctx: AgentContext,
    *,
    risks: list[RiskFinding],
    evidence: list[EvidenceItem],
    policy_matches: list[PolicyMatch],
    challenges: list[Challenge],
    verifications: list[ClaimVerification],
    assessment_context: str,
) -> StructuredResult[SynthesisNarrative]:
    """Write the analyst-facing narrative around an already-computed rating.

    ``assessment_context`` carries the score, level and every factor behind it,
    produced by the deterministic engine before this agent runs. The agent
    explains that result; it does not produce it.
    """
    user = f"""\
## Case
{ctx.case_summary}

## Computed assessment
This rating was calculated by the scoring engine from the findings, policy
triggers, verification outcomes and evidence coverage below. Explain it. Do not
restate it as your own conclusion and do not contradict it.

{assessment_context}

## Findings
{render_risks(risks)}

## Policy matches
{render_policy_matches(policy_matches)}

## Challenges raised
{render_challenges(challenges)}

## Verification outcomes
{render_verifications(verifications)}

## Evidence base
{render_evidence(evidence, include_quotes=False)}

Write the executive summary, key judgements, limitations, recommended follow-up
and - for each material finding - what evidence would raise or lower the
assessment."""

    return _run(ctx, SYNTHESISER, SynthesisNarrative, user, "synthesis")


__all__ = [
    "RiskAssessment",
    "analyse_policy",
    "analyse_risks",
    "challenge_findings",
    "extract_evidence",
    "plan_investigation",
    "synthesise_narrative",
    "verify_claims",
]

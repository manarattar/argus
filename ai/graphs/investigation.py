"""The investigation graph.

This is the orchestration layer: a LangGraph state machine whose nodes are the
agents, with the deterministic controls wired between them.

    plan -> extract -> [gate] -> risk -> policy -> challenge -> verify
         -> score -> synthesise -> HUMAN REVIEW

Three design decisions are worth stating explicitly, because they are the ones
an interviewer should ask about.

**Why a graph and not a chain.** The workflow is not linear in practice. It
branches when extraction produces nothing worth analysing, it must survive a
step failing without losing the work already done, and it has to stop in the
middle and resume hours later once a human has reviewed it. A checkpointed state
machine expresses all three directly; a chain of function calls expresses none
of them. See ADR-001.

**Why the sequence is sequential.** Policy analysis and challenging could run
concurrently - they both depend only on findings and evidence. They do not,
because the value of concurrency here is a couple of seconds, while the cost is
a non-deterministic trace, and the trace is a product feature: analysts and
auditors read it. Determinism won. That is a considered trade-off, not an
omission.

**Why the human gate is a graph interrupt.** Stopping for review is not a UI
convention that a caller could forget to honour - it is a structural property of
the workflow. The graph ends at ``awaiting_human_review`` and the finalisation
path is a separate entry point that cannot be reached without a recorded human
decision. See ADR-003.

Failure handling: a step that fails is recorded as failed and the graph
continues where the remaining work is still meaningful. It never substitutes
content of its own, and a failure is always visible in the trace and on the
investigation screen.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ai.agents.context import AgentContext
from ai.agents.investigators import (
    analyse_policy,
    analyse_risks,
    challenge_findings,
    extract_evidence,
    plan_investigation,
    synthesise_narrative,
    verify_claims,
)
from ai.domain import DomainConfig
from ai.graphs.integrity import (
    IntegrityReport,
    enforce_evidence_references,
    enforce_risk_references,
    filter_grounded_evidence,
)
from ai.graphs.state import InvestigationState, RejectedEvidence, StepTrace
from ai.providers.base import LLMError
from ai.providers.structured import SchemaValidationFailure, StructuredResult
from ai.schemas.enums import StepStatus, SupportStatus
from ai.schemas.models import RiskAssessment
from ai.scoring.coverage import assess_coverage, evaluate_escalation
from ai.scoring.engine import ScoreResult, compute_assessment_score
from ai.scoring.uncertainty import assess_evidence_strength

T = TypeVar("T")

# Minimum grounded evidence before risk analysis is worth attempting. Below
# this the honest outcome is "the file does not support an assessment", not a
# thin set of findings dressed up as one.
MIN_EVIDENCE_FOR_ANALYSIS = 2


class InvestigationRunner:
    """Builds and executes the investigation graph for one case.

    Holds the agent context and the trace; the graph nodes are bound methods so
    they can record steps without threading a logger through the state.
    """

    def __init__(
        self,
        ctx: AgentContext,
        domain: DomainConfig,
        *,
        on_step: Callable[[StepTrace], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.domain = domain
        self._on_step = on_step
        self._integrity = IntegrityReport()
        # LangGraph only propagates keys declared on the state TypedDict, so the
        # computed score is carried on the runner rather than smuggled through
        # the state as an undeclared key (where it would be silently dropped).
        self._score: ScoreResult | None = None

    # -- step plumbing ---------------------------------------------------

    def _begin(
        self, state: InvestigationState, step_id: str, name: str, capability: str
    ) -> StepTrace:
        trace = StepTrace(step_id=step_id, name=name, capability=capability)
        trace.status = StepStatus.RUNNING
        state["steps"].append(trace)
        return trace

    def _record_llm(self, trace: StepTrace, result: StructuredResult[Any], prompt_ref: str) -> None:
        trace.prompt_reference = prompt_ref
        trace.model = result.model
        trace.attempts = result.attempts
        trace.retries = max(0, result.attempts - 1)
        trace.input_tokens = result.input_tokens
        trace.output_tokens = result.output_tokens
        trace.cost_usd = result.total_cost_usd
        trace.replayed = result.replayed

    def _fail(self, state: InvestigationState, trace: StepTrace, exc: Exception) -> None:
        """Record a step failure without inventing a result for it."""
        trace.error = f"{type(exc).__name__}: {exc}"
        trace.finish(StepStatus.FAILED, "Step failed - see error detail.")
        state["errors"].append(f"{trace.name}: {trace.error}")
        self._emit(trace)

    def _emit(self, trace: StepTrace) -> None:
        if self._on_step is not None:
            self._on_step(trace)

    # -- nodes -----------------------------------------------------------

    def node_plan(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import PLANNER

        trace = self._begin(state, "plan", "Intake & Planning", "planning")
        try:
            result = plan_investigation(self.ctx)
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            state["status"] = "failed"
            return state

        plan = result.value
        self._record_llm(trace, result, PLANNER.reference)
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Planned {len(plan.tasks)} task(s) across "
            f"{len(plan.priority_categories)} priority categor"
            f"{'y' if len(plan.priority_categories) == 1 else 'ies'}; "
            f"{len(plan.information_gaps)} information gap(s) recorded.",
            tasks=len(plan.tasks),
            gaps=len(plan.information_gaps),
            priority_categories=[c.value for c in plan.priority_categories],
        )
        self._emit(trace)
        state["plan"] = plan
        state["status"] = "running"
        return state

    def node_extract(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import EVIDENCE_EXTRACTOR

        trace = self._begin(state, "evidence", "Evidence Extraction", "evidence_extraction")
        plan = state["plan"]
        if plan is None:
            trace.finish(StepStatus.SKIPPED, "No plan available; extraction skipped.")
            self._emit(trace)
            return state

        try:
            result, quality = extract_evidence(self.ctx, plan)
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            # Extraction is the foundation every later step builds on. If it
            # failed there is nothing to analyse, score or narrate, so the run
            # halts here rather than spending model calls describing an empty
            # result. The failure stays visible in the trace.
            state["status"] = "failed"
            return state

        proposed = result.value.evidence
        # The grounding control: every quote is re-checked against stored text.
        grounded = filter_grounded_evidence(proposed, self.ctx.chunk_texts("case"), self._integrity)
        rejected = [
            RejectedEvidence(
                evidence_id=eid,
                statement=next((e.statement for e in proposed if e.evidence_id == eid), ""),
                reason=reason,
                grounding_score=score,
                cited_chunk_id=next((e.chunk_id for e in proposed if e.evidence_id == eid), ""),
            )
            for eid, reason, score in self._integrity.dropped_evidence
        ]

        self._record_llm(trace, result, EVIDENCE_EXTRACTOR.reference)
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Retrieved {self.ctx.metrics.get('chunks_retrieved', 0)} section(s); "
            f"kept {len(grounded)} of {len(proposed)} extracted item(s) after "
            f"grounding verification.",
            proposed=len(proposed),
            grounded=len(grounded),
            rejected=len(rejected),
            retrieval_quality=quality,
            integrity=self._integrity.to_dict(),
        )
        self._emit(trace)

        state["evidence"] = grounded
        state["rejected_evidence"] = rejected
        state["retrieval_quality"] = quality
        return state

    def node_risk(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import RISK_SPECIALIST

        trace = self._begin(state, "risk", "Risk Specialist", "risk_analysis")
        plan, evidence = state["plan"], state["evidence"]
        if plan is None:
            trace.finish(StepStatus.SKIPPED, "No plan available.")
            self._emit(trace)
            return state

        try:
            result = analyse_risks(self.ctx, plan, evidence)
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            return state

        analysis = result.value
        self._record_llm(trace, result, RISK_SPECIALIST.reference)
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Generated {len(analysis.risks)} finding(s); "
            f"{len(analysis.categories_reviewed_without_finding)} categor"
            f"{'y' if len(analysis.categories_reviewed_without_finding) == 1 else 'ies'} "
            "reviewed without a finding.",
            findings=len(analysis.risks),
            categories=[r.category.value for r in analysis.risks],
        )
        self._emit(trace)
        state["risks"] = analysis.risks
        return state

    def node_policy(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import POLICY_ANALYST

        trace = self._begin(state, "policy", "Policy Analyst", "policy_retrieval")
        if not state["risks"]:
            trace.finish(StepStatus.SKIPPED, "No findings to assess against policy.")
            self._emit(trace)
            return state

        try:
            result = analyse_policy(self.ctx, state["risks"], state["evidence"])
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            return state

        matches = result.value.matches
        triggers = [m for m in matches if m.trigger_type != "informational"]
        self._record_llm(trace, result, POLICY_ANALYST.reference)
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Matched {len(matches)} policy clause(s), of which {len(triggers)} "
            "represent a trigger or potential breach.",
            matches=len(matches),
            clauses=sorted({m.clause_reference for m in matches}),
            policy_chunks=self.ctx.metrics.get("policy_chunks_retrieved", 0),
        )
        self._emit(trace)
        state["policy_matches"] = matches
        return state

    def node_challenge(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import CHALLENGER

        trace = self._begin(state, "challenge", "Challenger", "challenge")
        if not state["risks"]:
            trace.finish(StepStatus.SKIPPED, "No findings to challenge.")
            self._emit(trace)
            return state

        try:
            result = challenge_findings(self.ctx, state["risks"], state["evidence"])
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            return state

        report = result.value
        unresolved = [c for c in report.challenges if c.unresolved]
        self._record_llm(trace, result, CHALLENGER.reference)
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Raised {len(report.challenges)} challenge(s); {len(unresolved)} "
            "could not be resolved on the available evidence.",
            challenges=len(report.challenges),
            unresolved=len(unresolved),
            types=sorted({c.challenge_type for c in report.challenges}),
        )
        self._emit(trace)
        state["challenges"] = report.challenges
        return state

    def node_verify(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import VERIFIER

        trace = self._begin(state, "verify", "Evidence Verifier", "verification")
        if not state["risks"]:
            trace.finish(StepStatus.SKIPPED, "No findings to verify.")
            self._emit(trace)
            return state

        try:
            result = verify_claims(self.ctx, state["risks"], state["evidence"])
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            return state

        verifications = result.value.verifications
        weak = [
            v
            for v in verifications
            if v.status in {SupportStatus.PARTIALLY_SUPPORTED, SupportStatus.UNSUPPORTED}
        ]
        self._record_llm(trace, result, VERIFIER.reference)
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Checked {len(verifications)} claim(s); {len(weak)} were not fully "
            "supported by their citations.",
            verified=len(verifications),
            not_fully_supported=len(weak),
        )
        self._emit(trace)
        state["verifications"] = verifications
        return state

    def node_score(self, state: InvestigationState) -> InvestigationState:
        """Deterministic consolidation. No model call happens here.

        Runs integrity enforcement across every agent output, grades each
        finding's evidence, computes coverage, and produces the rating.
        """
        trace = self._begin(state, "score", "Scoring & Integrity", "scoring")
        started = time.perf_counter()

        valid_evidence_ids = {e.evidence_id for e in state["evidence"]}
        risks, challenges, verifications = enforce_evidence_references(
            risks=state["risks"],
            challenges=state["challenges"],
            verifications=state["verifications"],
            valid_evidence_ids=valid_evidence_ids,
            report=self._integrity,
        )
        valid_risk_ids = {r.risk_id for r in risks}
        policy_matches, challenges, verifications = enforce_risk_references(
            valid_risk_ids=valid_risk_ids,
            policy_matches=state["policy_matches"],
            challenges=challenges,
            verifications=verifications,
            report=self._integrity,
        )

        evidence_by_id = {e.evidence_id: e for e in state["evidence"]}
        verdicts = {v.risk_id: v.status for v in verifications}
        plan = state["plan"]
        blocked_categories = (
            {c for gap in plan.information_gaps for c in gap.blocks_categories} if plan else set()
        )

        graded = []
        for risk in risks:
            strength = assess_evidence_strength(
                risk,
                evidence_by_id,
                verifier_status=verdicts.get(risk.risk_id),
                blocking_gap=risk.category in blocked_categories,
            )
            graded.append(
                risk.model_copy(
                    update={
                        "evidence_strength": strength.strength,
                        "strength_rationale": strength.rationale,
                        "inherent_score": float(risk.severity.ordinal * risk.likelihood.ordinal),
                    }
                )
            )

        coverage = assess_coverage(self.domain, state["evidence"])
        score = compute_assessment_score(
            graded,
            policy_matches=policy_matches,
            verifications=verifications,
            challenges=challenges,
            coverage=coverage,
        )

        state["risks"] = graded
        state["policy_matches"] = policy_matches
        state["challenges"] = challenges
        state["verifications"] = verifications
        state["coverage"] = coverage
        state["escalation_reasons"] = evaluate_escalation(
            self.domain, graded, policy_matches, score.overall_level
        )
        self._score = score

        trace.finish(
            StepStatus.SUCCEEDED,
            f"Computed provisional rating {score.overall_level.label} "
            f"({score.overall_score:.0f}/100) from {len(graded)} finding(s). "
            f"{self._integrity.summary()}",
            overall_level=score.overall_level.value,
            overall_score=score.overall_score,
            integrity=self._integrity.to_dict(),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        self._emit(trace)
        return state

    def node_synthesise(self, state: InvestigationState) -> InvestigationState:
        from ai.prompts.library import SYNTHESISER

        trace = self._begin(state, "synthesis", "Risk Synthesis", "synthesis")
        score = self._score
        if score is None:
            trace.finish(StepStatus.SKIPPED, "No computed score to narrate.")
            self._emit(trace)
            return state

        factor_lines = "\n".join(
            f"- {f.label}: {f.contribution:+.1f} points ({f.direction}) - {f.detail}"
            for f in score.factors
        )
        coverage_lines = "\n".join(
            f"- {c.category.label}: {c.status.value} - {c.expected}" for c in state["coverage"]
        )
        assessment_context = (
            f"Overall rating: {score.overall_level.label} "
            f"({score.overall_score:.1f}/100)\n"
            f"Portfolio evidence strength: {score.portfolio_strength.label}\n\n"
            f"Factors:\n{factor_lines}\n\n"
            f"Evidence coverage:\n{coverage_lines}"
        )

        try:
            result = synthesise_narrative(
                self.ctx,
                risks=state["risks"],
                evidence=state["evidence"],
                policy_matches=state["policy_matches"],
                challenges=state["challenges"],
                verifications=state["verifications"],
                assessment_context=assessment_context,
            )
        except (LLMError, SchemaValidationFailure) as exc:
            self._fail(state, trace, exc)
            # The rating still stands - it was computed deterministically. Only
            # the narrative is missing, and the UI says so rather than
            # presenting a summary that was never written.
            state["assessment"] = None
            state["status"] = "awaiting_human_review"
            return state

        narrative = result.value
        self._record_llm(trace, result, SYNTHESISER.reference)

        state["assessment"] = RiskAssessment(
            overall_level=score.overall_level,
            overall_score=score.overall_score,
            score_factors=score.factors,
            category_levels=score.category_levels,
            evidence_strength=score.portfolio_strength,
            coverage=state["coverage"],
            narrative=narrative,
        )
        trace.finish(
            StepStatus.SUCCEEDED,
            f"Drafted assessment narrative with {len(narrative.key_judgements)} key "
            f"judgement(s) and {len(narrative.mind_changers)} mind-changer(s).",
            key_judgements=len(narrative.key_judgements),
            limitations=len(narrative.limitations),
        )
        self._emit(trace)
        state["status"] = "awaiting_human_review"
        return state

    # -- routing ---------------------------------------------------------

    @staticmethod
    def _after_extract(state: InvestigationState) -> str:
        """Stop early rather than analyse a file that yielded nothing."""
        if state["status"] == "failed":
            return "halt"
        return "analyse" if len(state["evidence"]) >= MIN_EVIDENCE_FOR_ANALYSIS else "score"

    @staticmethod
    def _after_plan(state: InvestigationState) -> str:
        return "halt" if state["status"] == "failed" else "extract"

    # -- assembly --------------------------------------------------------

    def build(self) -> CompiledStateGraph:
        """Compile the graph. Terminates at the human review gate."""
        graph = StateGraph(InvestigationState)
        graph.add_node("intake", self.node_plan)
        graph.add_node("extract", self.node_extract)
        graph.add_node("risk", self.node_risk)
        graph.add_node("policy", self.node_policy)
        graph.add_node("challenge", self.node_challenge)
        graph.add_node("verify", self.node_verify)
        graph.add_node("score", self.node_score)
        graph.add_node("synthesise", self.node_synthesise)

        graph.set_entry_point("intake")
        graph.add_conditional_edges("intake", self._after_plan, {"extract": "extract", "halt": END})
        graph.add_conditional_edges(
            "extract",
            self._after_extract,
            {"analyse": "risk", "score": "score", "halt": END},
        )
        graph.add_edge("risk", "policy")
        graph.add_edge("policy", "challenge")
        graph.add_edge("challenge", "verify")
        graph.add_edge("verify", "score")
        graph.add_edge("score", "synthesise")
        # The graph deliberately ends here. Finalisation requires a recorded
        # human decision and is a separate entry point (ADR-003).
        graph.add_edge("synthesise", END)
        return graph.compile()

    def run(self, state: InvestigationState) -> InvestigationState:
        """Execute the graph to the human review gate."""
        compiled = self.build()
        # Node count plus headroom; guards against a routing mistake looping.
        final = cast(InvestigationState, compiled.invoke(state, {"recursion_limit": 24}))
        if final["status"] not in {"failed", "awaiting_human_review"}:
            final["status"] = "awaiting_human_review"
        return final

    @property
    def integrity(self) -> IntegrityReport:
        return self._integrity

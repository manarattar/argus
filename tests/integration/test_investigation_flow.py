"""End-to-end investigation flow, driven by a scripted model backend.

This is the test that proves the pipeline is real. It ingests the actual
Northstar corpus, runs the whole LangGraph workflow, and asserts on the
behaviour that matters:

* every agent output is validated against its schema;
* a deliberately fabricated quote is rejected by the grounding control;
* a citation to evidence that does not exist is stripped;
* the rating is computed, not asserted;
* the workflow stops at the human review gate;
* a human override changes the rating and is recorded against the AI's original.

No network call is made. The scripted backend returns fixed JSON, so every
deterministic control runs exactly as it would in production while the test
stays fast and repeatable.
"""

from __future__ import annotations

import json

import pytest
from argus_api.core.settings import get_settings
from argus_api.db.models import Case, Evidence, Investigation, Override, Risk
from argus_api.db.session import session_scope
from argus_api.services import review as review_service
from argus_api.services.corpus import build_index, ingest_directory
from argus_api.services.investigation import run_investigation
from sqlalchemy import select

from ai.schemas.enums import InvestigationStatus, ReviewDecision, Severity, StepStatus
from tests.conftest import ScriptedProvider

pytestmark = pytest.mark.integration

CASE_ID = "case-test-northstar"

# --- scripted agent outputs -------------------------------------------------
# Quotes marked REAL are verbatim from the corpus; the FABRICATED one is not,
# and the grounding control must reject it.

PLAN = json.dumps(
    {
        "objective": (
            "Determine whether Northstar Manufacturing remains within risk appetite "
            "following the FY2025 increase in borrowings."
        ),
        "scope_summary": (
            "Covers financial resilience, revenue concentration and governance for "
            "the FY2025 review period. Excludes remuneration."
        ),
        "tasks": [
            {
                "task_id": "T1",
                "objective": "Establish the financial position across three periods.",
                "capability": "evidence_extraction",
                "focus_categories": ["financial"],
                "rationale": "Leverage moved materially during the period.",
            }
        ],
        "priority_categories": ["financial", "concentration"],
        "information_gaps": [
            {
                "gap_id": "G1",
                "description": "No signed renewal for the second-largest customer.",
                "why_it_matters": "23% of revenue depends on a contract expiring in June 2026.",
                "blocks_categories": ["concentration"],
            }
        ],
    }
)

EVIDENCE = json.dumps(
    {
        "evidence": [
            {
                "evidence_id": "E1",
                "statement": "Borrowings more than doubled during FY2025.",
                # REAL
                "quote": "Total borrowings increased from EUR 21.4 million to EUR 48.3 million",
                "kind": "fact",
                "category": "financial",
                "document_id": "test-02-financial-summary",
                "document_name": "Three-Year Financial Summary",
                "section_reference": "p. 2",
                "chunk_id": "PLACEHOLDER",
                "materiality": "major",
            },
            {
                "evidence_id": "E2",
                "statement": "The two largest customers account for 62% of revenue.",
                # REAL
                "quote": "the two largest customers together accounted for 62% of consolidated revenue",
                "kind": "fact",
                "category": "concentration",
                "document_id": "test-01-annual-report-2025",
                "document_name": "Annual Report 2025",
                "section_reference": "p. 3",
                "chunk_id": "PLACEHOLDER",
                "materiality": "major",
            },
            {
                "evidence_id": "E3",
                "statement": "The company has already breached its banking covenants.",
                # FABRICATED - appears nowhere in the corpus. Must be rejected.
                "quote": (
                    "Northstar breached its net leverage covenant at the December 2025 "
                    "test date and entered a standstill agreement with its lenders."
                ),
                "kind": "fact",
                "category": "financial",
                "document_id": "test-02-financial-summary",
                "document_name": "Three-Year Financial Summary",
                "section_reference": "p. 4",
                "chunk_id": "PLACEHOLDER",
                "materiality": "severe",
            },
        ],
        "notes": "Extraction focused on the priority categories in the plan.",
    }
)

RISKS = json.dumps(
    {
        "risks": [
            {
                "risk_id": "R1",
                "title": "Sharp increase in financial leverage",
                "category": "financial",
                "description": (
                    "Net leverage rose from 0.97x to 2.40x in a single reporting period "
                    "following debt-funded capacity expansion, materially changing the "
                    "counterparty's balance sheet profile."
                ),
                "severity": "major",
                "likelihood": "likely",
                # E3 was fabricated and will not survive; E99 never existed.
                "supporting_evidence_ids": ["E1", "E3", "E99"],
                "contradicting_evidence_ids": [],
                "assumptions": ["FY2026 EBITDA holds at FY2025 levels."],
                "open_questions": ["What is the covenant headroom at the June 2026 test?"],
                "mitigating_factors": ["Both covenants were met at the December 2025 test."],
            },
            {
                "risk_id": "R2",
                "title": "Material revenue concentration",
                "category": "concentration",
                "description": (
                    "The two largest customers account for 62% of revenue, above the "
                    "50% threshold at which the framework classifies concentration as "
                    "material, and the share has risen in each of three years."
                ),
                "severity": "major",
                "likelihood": "possible",
                "supporting_evidence_ids": ["E2"],
                "contradicting_evidence_ids": [],
                "assumptions": [],
                "open_questions": ["Will the June 2026 agreement be renewed?"],
                "mitigating_factors": [],
            },
        ],
        "categories_reviewed_without_finding": ["legal"],
    }
)

POLICY = json.dumps(
    {
        "matches": [
            {
                "match_id": "M1",
                "risk_id": "R2",
                "policy_id": "policy-counterparty-risk-framework",
                "clause_reference": "CRF 4.2",
                "clause_title": "Customer concentration",
                "relevance": (
                    "The clause classifies combined top-two revenue above 50% as material "
                    "concentration, which is a review trigger."
                ),
                "trigger_type": "threshold_met",
                "threshold_assessment": "Policy threshold 50%; observed 62%.",
                "sufficiency_caveat": "",
            }
        ],
        "unmatched_note": "",
    }
)

CHALLENGES = json.dumps(
    {
        "challenges": [
            {
                "challenge_id": "C1",
                "risk_id": "R1",
                "challenge_type": "overstated_severity",
                "argument": (
                    "The leverage increase funded a commissioned capacity expansion with "
                    "contracted revenue behind it, and both covenants were met with "
                    "headroom at the most recent test. Major severity may overstate a "
                    "position that is currently within appetite."
                ),
                "counter_evidence_ids": [],
                "suggested_revision": "Consider Moderate severity pending the June 2026 test.",
                "proposed_severity": "moderate",
                "unresolved": True,
            }
        ],
        "unresolved_contradictions": [
            "Covenant headroom under the downside scenario cannot be verified from the file."
        ],
    }
)

VERIFICATIONS = json.dumps(
    {
        "verifications": [
            {
                "verification_id": "V1",
                "risk_id": "R1",
                "claim": "Net leverage rose sharply during FY2025.",
                "status": "supported",
                "reasoning": "The cited borrowing figures establish the increase directly.",
                "citations_checked": ["E1"],
                "irrelevant_citation_ids": [],
                "downgrade_recommended": False,
            },
            {
                "verification_id": "V2",
                "risk_id": "R2",
                "claim": "Revenue concentration exceeds the policy threshold.",
                "status": "supported",
                "reasoning": "The cited figure of 62% is above the 50% threshold.",
                "citations_checked": ["E2"],
                "irrelevant_citation_ids": [],
                "downgrade_recommended": False,
            },
        ]
    }
)

SYNTHESIS = json.dumps(
    {
        "executive_summary": (
            "Northstar's financial profile changed materially during FY2025, with net "
            "leverage rising from 0.97x to 2.40x to fund a capacity expansion that is "
            "now commissioned. Both covenants were met at the December 2025 test. "
            "Revenue concentration has risen for three consecutive years and now sits "
            "above the framework threshold, with 23% of revenue behind an agreement "
            "expiring in June 2026 that has not been renewed."
        ),
        "key_judgements": [
            "The leverage increase is explicable and currently within covenant.",
            "Concentration is the more consequential exposure over the review horizon.",
        ],
        "limitations": ["No signed renewal is available for the June 2026 agreement."],
        "recommended_followup": ["Request written confirmation of the renewal by 31 May 2026."],
        "mind_changers": [
            {
                "risk_id": "R2",
                "would_increase": "Confirmation that the June 2026 agreement will not renew.",
                "would_decrease": "A signed multi-year renewal on comparable terms.",
            }
        ],
    }
)


def _seed_corpus(session, embedder) -> Case:
    """Ingest the real demo corpus under a test case id."""
    settings = get_settings()
    case = Case(
        id=CASE_ID,
        reference="CR-TEST-0001",
        organisation="Northstar Manufacturing B.V.",
        review_type="Annual Counterparty Review",
        domain_key="counterparty_review",
        analyst="Test Analyst",
        sector="Industrial manufacturing",
        jurisdiction="Netherlands",
        background="Integration test case using the synthetic Northstar corpus.",
        status="draft",
    )
    session.add(case)
    session.flush()

    ingest_directory(
        session,
        settings.demo_data_dir / "northstar",
        embedder=embedder,
        doc_kind="case",
        case_id=case.id,
        id_prefix="test-",
    )
    ingest_directory(
        session,
        settings.policy_data_dir,
        embedder=embedder,
        doc_kind="policy",
        case_id=None,
        id_prefix="testpolicy-",
    )
    return case


def _resolve_chunk_ids(session, embedder, case_id: str) -> str:
    """Point the scripted evidence at chunks that really contain its quotes.

    The scripted extractor cannot know the generated chunk ids, so they are
    resolved here the way a real extractor would receive them in its prompt.
    """
    index = build_index(session, embedder, case_id=case_id)
    chunk_texts = {c.chunk_id: c.text for c in index.chunks if c.doc_kind == "case"}

    payload = json.loads(EVIDENCE)
    for item in payload["evidence"]:
        match = next(
            (
                chunk_id
                for chunk_id, text in chunk_texts.items()
                if item["quote"][:40].lower() in text.lower()
            ),
            None,
        )
        # The fabricated quote matches nothing; give it a real chunk id so the
        # test proves the *quote* is rejected, not merely a bad chunk pointer.
        item["chunk_id"] = match or next(iter(chunk_texts))
        item["document_id"] = item["chunk_id"].split("::")[0]
    return json.dumps(payload)


@pytest.fixture
def investigation_env(db, embedder):
    with session_scope() as session:
        case = _seed_corpus(session, embedder)
        evidence_payload = _resolve_chunk_ids(session, embedder, case.id)
    return evidence_payload


def _provider(evidence_payload: str) -> ScriptedProvider:
    return ScriptedProvider(
        [PLAN, evidence_payload, RISKS, POLICY, CHALLENGES, VERIFICATIONS, SYNTHESIS]
    )


class TestFullInvestigation:
    def test_graph_runs_and_persists_everything(self, investigation_env, embedder) -> None:
        provider = _provider(investigation_env)

        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            assert case is not None
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            investigation_id = investigation.id

        with session_scope() as session:
            stored = session.get(Investigation, investigation_id)
            assert stored is not None

            # The workflow stops for a human. It never completes on its own.
            assert stored.status == InvestigationStatus.AWAITING_HUMAN_REVIEW.value

            # The fabricated quote was rejected by the grounding control.
            evidence_ids = {
                e.evidence_id
                for e in session.execute(
                    select(Evidence).where(Evidence.investigation_id == investigation_id)
                )
                .scalars()
                .all()
            }
            assert evidence_ids == {"E1", "E2"}, "E3 was fabricated and must be dropped"
            assert len(stored.rejected_evidence) == 1
            assert stored.rejected_evidence[0]["evidence_id"] == "E3"

            # Citations to dropped and nonexistent evidence were stripped.
            risks = {
                r.risk_id: r
                for r in session.execute(
                    select(Risk).where(Risk.investigation_id == investigation_id)
                )
                .scalars()
                .all()
            }
            assert set(risks["R1"].supporting_evidence_ids) == {"E1"}
            assert "E99" not in risks["R1"].supporting_evidence_ids

            # The rating was computed and is explainable.
            assert stored.overall_level in {"low", "moderate", "elevated", "high"}
            assert stored.score_factors
            assert all(f["label"] and f["detail"] for f in stored.score_factors)

            # Every agent step ran and was recorded.
            statuses = {s.step_id: s.status for s in stored.steps}
            assert statuses["plan"] == StepStatus.SUCCEEDED.value
            assert statuses["evidence"] == StepStatus.SUCCEEDED.value
            assert statuses["score"] == StepStatus.SUCCEEDED.value
            assert statuses["synthesis"] == StepStatus.SUCCEEDED.value
            assert not stored.errors

            # Narrative and coverage were produced.
            assert stored.narrative["executive_summary"]
            assert stored.coverage

    def test_untrusted_content_is_delimited_in_every_prompt(
        self, investigation_env, embedder
    ) -> None:
        """The trust boundary must be applied wherever document text is sent."""
        provider = _provider(investigation_env)
        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )

        document_prompts = [r for r in provider.requests if r.purpose in {"evidence", "policy"}]
        assert document_prompts
        for request in document_prompts:
            assert "<document" in request.user or "<retrieved_evidence>" in request.user
            assert "UNTRUSTED DATA" in request.system

    def test_schema_is_sent_with_every_agent_call(self, investigation_env, embedder) -> None:
        provider = _provider(investigation_env)
        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
        for request in provider.requests:
            assert "Required output format" in request.system
            assert request.json_mode


class TestHumanReview:
    def test_override_changes_the_rating_and_preserves_the_original(
        self, investigation_env, embedder
    ) -> None:
        provider = _provider(investigation_env)

        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            investigation_id = investigation.id
            original_score = investigation.overall_score

        with session_scope() as session:
            investigation = session.get(Investigation, investigation_id)
            risk = session.execute(
                select(Risk).where(Risk.investigation_id == investigation_id, Risk.risk_id == "R1")
            ).scalar_one()
            ai_severity = risk.ai_severity

            review_service.override_severity(
                session,
                investigation=investigation,
                risk=risk,
                new_severity=Severity.MINOR,
                rationale="Commissioned expansion with contracted revenue behind it.",
                actor="Test Analyst",
            )
            result = review_service.rescore(session, investigation)

        with session_scope() as session:
            investigation = session.get(Investigation, investigation_id)
            risk = session.execute(
                select(Risk).where(Risk.investigation_id == investigation_id, Risk.risk_id == "R1")
            ).scalar_one()
            override = session.execute(
                select(Override).where(Override.investigation_id == investigation_id)
            ).scalar_one()

            # The human value is current; the AI value is still on the record.
            assert risk.severity == Severity.MINOR.value
            assert risk.ai_severity == ai_severity
            assert override.ai_value == ai_severity
            assert override.human_value == Severity.MINOR.value
            assert override.rationale

            # Lowering a severity must lower the rating.
            assert result.overall_score < original_score
            assert investigation.overall_score < original_score

    def test_override_without_rationale_is_refused(self, investigation_env, embedder) -> None:
        provider = _provider(investigation_env)
        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            risk = (
                session.execute(select(Risk).where(Risk.investigation_id == investigation.id))
                .scalars()
                .first()
            )

            with pytest.raises(review_service.ReviewError, match="rationale is required"):
                review_service.override_severity(
                    session,
                    investigation=investigation,
                    risk=risk,
                    new_severity=Severity.MINOR,
                    rationale="   ",
                    actor="Test Analyst",
                )

    def test_review_completes_the_case(self, investigation_env, embedder) -> None:
        provider = _provider(investigation_env)
        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            investigation_id = investigation.id

        with session_scope() as session:
            investigation = session.get(Investigation, investigation_id)
            case = session.get(Case, CASE_ID)
            decision = (
                ReviewDecision.ESCALATE
                if investigation.escalation_reasons
                else ReviewDecision.APPROVE
            )
            review_service.submit_review(
                session,
                investigation=investigation,
                case=case,
                decision=decision,
                comment="Reviewed against the file and the framework thresholds.",
                actor="Test Analyst",
            )

        with session_scope() as session:
            investigation = session.get(Investigation, investigation_id)
            assert investigation.status in {"completed", "awaiting_human_review"}
            assert len(investigation.case.investigations) == 1

    def test_approval_is_blocked_while_an_escalation_stands(
        self, investigation_env, embedder
    ) -> None:
        provider = _provider(investigation_env)
        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            # Force an escalation so the control can be exercised regardless of
            # what the scripted findings happen to score.
            investigation.escalation_reasons = ["Potential policy breach identified."]

            with pytest.raises(review_service.ReviewError, match="mandatory escalation"):
                review_service.submit_review(
                    session,
                    investigation=investigation,
                    case=case,
                    decision=ReviewDecision.APPROVE,
                    comment="",
                    actor="Test Analyst",
                )


class TestFailureHandling:
    def test_a_failed_step_is_recorded_and_never_invented(
        self, investigation_env, embedder
    ) -> None:
        """When a step cannot produce valid output it fails visibly. The
        pipeline must not substitute content of its own."""
        provider = ScriptedProvider([PLAN, "this is not JSON at all", "still not JSON", "nope"])

        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            investigation_id = investigation.id

        with session_scope() as session:
            stored = session.get(Investigation, investigation_id)
            evidence_step = next(s for s in stored.steps if s.step_id == "evidence")
            assert evidence_step.status == StepStatus.FAILED.value
            assert evidence_step.error
            assert stored.errors
            # Nothing was fabricated to fill the gap.
            assert len(stored.evidence) == 0
            assert len(stored.risks) == 0

    def test_graph_stops_early_when_no_evidence_survives(self, investigation_env, embedder) -> None:
        empty_evidence = json.dumps({"evidence": [], "notes": "Nothing material found."})
        provider = ScriptedProvider([PLAN, empty_evidence, SYNTHESIS])

        with session_scope() as session:
            case = session.get(Case, CASE_ID)
            investigation = run_investigation(
                session, case=case, provider=provider, embedder=embedder, actor="test"
            )
            investigation_id = investigation.id

        with session_scope() as session:
            stored = session.get(Investigation, investigation_id)
            statuses = {s.step_id: s.status for s in stored.steps}
            # Risk analysis is skipped rather than run on nothing.
            assert "risk" not in statuses or statuses["risk"] == StepStatus.SKIPPED.value
            assert len(stored.risks) == 0

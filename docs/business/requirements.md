# Requirements

> Fictional requirements written for the ARGUS demonstration.

Identifiers are stable and referenced from the traceability matrix at the end,
which is the part of this document that matters: it connects every business
requirement to the feature that delivers it, the component that implements it,
and the test or metric that proves it.

---

## 1. Business requirements

| ID | Requirement | Rationale |
|---|---|---|
| **BR-1** | Reduce analyst preparation time per assessment without reducing review depth | Preparation is the compressible part; judgement is not |
| **BR-2** | Every conclusion must be traceable to a specific source location | Assessments are audited and challenged |
| **BR-3** | Counter-evidence must be surfaced as reliably as supporting evidence | Confirmation bias is the dominant analytical failure |
| **BR-4** | Uncertainty must be visible and interpretable | A reviewer must know how hard to push |
| **BR-5** | A named human must remain accountable for every assessment | Regulatory and institutional requirement |
| **BR-6** | Divergence between system and analyst must be measurable | The only honest read on whether the tool works |
| **BR-7** | Policy thresholds must be applied consistently | Manual recall drifts across analysts |
| **BR-8** | Missing information must be recorded explicitly | Absence is decision-relevant and easily overlooked |
| **BR-9** | The platform must extend to other review types without rebuild | Investment must amortise beyond one use case |
| **BR-10** | System quality must be measurable and reproducible | Required to govern an AI system in production |

---

## 2. User requirements

| ID | As a… | I need to… | So that… |
|---|---|---|---|
| **UR-1** | Analyst | See material evidence with its source locator | I can cite it without reopening the document |
| **UR-2** | Analyst | See evidence that contradicts a finding | I am not surprised in review |
| **UR-3** | Analyst | See how strongly a finding is evidenced, and why | I know where to spend my time |
| **UR-4** | Analyst | Change a severity and record why | The assessment reflects my judgement |
| **UR-5** | Analyst | Ask for the strongest case against a finding | I can stress-test my own conclusion |
| **UR-6** | Analyst | Ask questions of the case record | I can interrogate without re-reading |
| **UR-7** | Analyst | See what the file is missing | I can request it before review |
| **UR-8** | Reviewer | See the assessment and its drivers immediately | I can triage sixty packs a month |
| **UR-9** | Reviewer | See where the analyst overrode the system | I know where judgement was applied |
| **UR-10** | Reviewer | Trace any conclusion to a page | I can verify rather than trust |
| **UR-11** | Reviewer | See unresolved contradictions | I can probe the weakest point |
| **UR-12** | Product Owner | See override and adoption rates | I can tell whether it is working |
| **UR-13** | Product Owner | See cost per investigation | I can justify the spend |
| **UR-14** | Product Owner | Run a reproducible evaluation | I can govern quality over time |
| **UR-15** | Engineer | Add a review type by configuration | I do not fork the pipeline |
| **UR-16** | Engineer | Swap model provider without code change | We are not locked to a vendor |

---

## 3. Functional requirements

| ID | Requirement | Acceptance criteria |
|---|---|---|
| **FR-1** | Ingest case documents into retrievable, citable chunks | Chunks carry document, section and page; citation keys are deterministic |
| **FR-2** | Retrieve relevant sections for a query | Hybrid keyword + vector; retrieval quality reported with results |
| **FR-3** | Extract evidence with verbatim quotes | Each item carries quote, statement, category, source, and fact/interpretation |
| **FR-4** | Verify every quote against its source before use | Unverifiable evidence is discarded before downstream agents and retained as rejected |
| **FR-5** | Identify risks citing evidence by identifier | Findings carry supporting and contradicting identifiers; unresolvable ones are stripped |
| **FR-6** | Match findings to policy clauses | Clause reference, title, relationship type, threshold assessment, sufficiency caveat |
| **FR-7** | Generate challenges against findings | Typed challenges with counter-evidence and a suggested revision; unresolved ones flagged |
| **FR-8** | Verify each finding against its citations | Four-valued verdict with reasoning and irrelevant-citation identification |
| **FR-9** | Compute an explainable rating | Rating derived from named factors; not model-generated; factors sum to the score |
| **FR-10** | Assess evidence strength per finding | Interpretable band with rationale, from observable signals |
| **FR-11** | Measure investigation completeness | Coverage per expected evidence category, against domain configuration |
| **FR-12** | Stop for human review | No path completes an assessment without a recorded human decision |
| **FR-13** | Record overrides with both values | AI recommendation, human decision, mandatory rationale, actor, timestamp |
| **FR-14** | Recompute the rating after an override | Same engine; change surfaced to the analyst with factors |
| **FR-15** | Enforce escalation rules | Rule-driven; approval blocked while an escalation stands |
| **FR-16** | Maintain an append-only audit trail | Single write path; no update or delete code exists |
| **FR-17** | Generate an assessment report | All required sections; PDF export; empty sections state "none recorded" |
| **FR-18** | Answer questions from the case record | Citations resolved against stored evidence; refuses when unanswerable |
| **FR-19** | Visualise decision lineage | Rating → finding → evidence → document, and finding → policy |
| **FR-20** | Model scenarios over structured variables | Declared variables only; deterministic recomputation; labelled a simulation |
| **FR-21** | Run a reproducible evaluation suite | Per-category metrics; skipped cases never counted as passes |
| **FR-22** | Expose operational metrics | Executions, failures, retries, latency, tokens, cost, override rate |
| **FR-23** | Model the business case | User-editable assumptions with sensitivity analysis; labelled illustrative |
| **FR-24** | Operate without a model API key | Recorded responses replayed; all deterministic layers execute; mode stated in the UI |

---

## 4. Non-functional requirements

| ID | Requirement | Target | Status |
|---|---|---|---|
| **NFR-1** | Investigation latency | < 60s for a six-document case | Met (seconds in Demo Mode; model-bound live) |
| **NFR-2** | Page interaction latency | < 200ms for stored data | Met |
| **NFR-3** | First-run experience | Working app with no account or container | Met |
| **NFR-4** | Reproducibility | Identical findings produce an identical rating | Met — deterministic engine, temperature 0 |
| **NFR-5** | Portability | SQLite and PostgreSQL on identical code paths | Met |
| **NFR-6** | Provider independence | No vendor SDK outside `ai/providers/` | Met |
| **NFR-7** | Type safety | Strict TypeScript; typed Python boundaries | Met |
| **NFR-8** | Accessibility | Keyboard navigable; meaning never carried by colour alone | Partially met — no formal audit performed |
| **NFR-9** | Observability | Every step traced with cost and outcome | Met |
| **NFR-10** | Security baseline | No secrets committed; bounded input; safe errors; headers set | Met for a prototype; enterprise gaps documented |
| **NFR-11** | Auditability | Every state change attributable to an actor | Met |

---

## 5. AI-specific requirements

| ID | Requirement | How it is satisfied |
|---|---|---|
| **AIR-1** | No fabricated citations | Quotes re-verified against stored source; identifiers checked by set membership |
| **AIR-2** | Structured output only | Pydantic validation with error-feedback retry; visible failure after budget |
| **AIR-3** | The rating is not model-generated | Deterministic engine consumes ordinal judgements only |
| **AIR-4** | No pseudo-precise confidence | Interpretable bands from observable signals, with rationale |
| **AIR-5** | Adversarial self-check | Dedicated Challenger agent; agreement counts as failure of the role |
| **AIR-6** | Claim verification | Verifier checks claim against citations; downgrades recorded |
| **AIR-7** | Untrusted document content | Delimited blocks; instruction-vs-data boundary in every prompt |
| **AIR-8** | Injection resistance is tested | Structural and behavioural evaluation cases |
| **AIR-9** | No chain-of-thought exposure | Traces record actions and outcomes only; reasoning is not stored |
| **AIR-10** | Graceful model failure | Typed error taxonomy; failed steps recorded, never substituted |
| **AIR-11** | Prompt versioning | Versioned library; reference recorded on every step |
| **AIR-12** | Cost accountability | Tokens and estimated cost per step, labelled as estimates |

---

## 6. Requirements traceability matrix

The connective tissue between the business case and the codebase.

| Business req | Product feature | Technical component | Validation |
|---|---|---|---|
| **BR-1** Reduce preparation time | Automated investigation; structured findings | `ai/graphs/investigation.py` | Value Case model; `test_investigation_flow.py` |
| **BR-2** Traceability | Verbatim quotes; source locators; Evidence Graph | `ai/tools/grounding.py`, `services/graph_view.py` | `test_grounding.py`; eval `gnd-001`…`gnd-007`; E2E lineage test |
| **BR-3** Counter-evidence | Contradicting evidence field; Challenger; on-demand challenge | `ai/agents/investigators.py` (Challenger) | Eval `con-001`, `con-002`; findings UI shows both columns |
| **BR-4** Visible uncertainty | Evidence-strength bands with rationale | `ai/scoring/uncertainty.py` | `test_uncertainty_and_value.py`; eval `unc-001`…`unc-005` |
| **BR-5** Human accountability | Review gate; blocked approval; audit trail | `services/review.py`, `ai/graphs/investigation.py` | `test_investigation_flow.py::TestHumanReview`; ADR-003 |
| **BR-6** Measurable divergence | Overrides store both values; override-rate metric | `db/models.py::Override`, `services/analytics.py` | `test_override_changes_the_rating_and_preserves_the_original` |
| **BR-7** Consistent policy | Policy RAG over numbered clauses; deterministic references | `ai/agents/investigators.py` (Policy), `data/policies/` | Eval `pol-001`…`pol-008` |
| **BR-8** Record what is missing | Information gaps; coverage panel; report limitations | `ai/scoring/coverage.py` | `test_uncertainty_and_value.py::TestCoverage`; eval `sco-005` |
| **BR-9** Extensible platform | `DomainConfig`; design-stage domains labelled | `ai/domain.py` | `TestDomainConfiguration`; `test_api.py::test_architecture_is_served_from_the_running_system` |
| **BR-10** Measurable quality | Evaluation Lab; coverage beside pass rate | `ai/evaluators/`, `services/evaluation.py` | `make eval`; `test_api.py::test_running_the_suite_reports_honest_metrics` |

### Reverse trace: control → requirement

| Control | Serves |
|---|---|
| Quote grounding | BR-2, AIR-1, FR-4 |
| Cross-reference integrity | BR-2, AIR-1, FR-5 |
| Schema validation | AIR-2, FR-3, NFR-7 |
| Deterministic scoring | BR-4, AIR-3, FR-9, NFR-4 |
| Uncertainty model | BR-4, AIR-4, FR-10 |
| Challenger agent | BR-3, AIR-5, FR-7 |
| Evidence Verifier | BR-2, AIR-6, FR-8 |
| Escalation rules | BR-5, FR-15 |
| Human review gate | BR-5, FR-12 |
| Override recording | BR-6, FR-13, FR-14 |
| Audit trail | BR-5, FR-16, NFR-11 |
| Prompt trust boundary | AIR-7, AIR-8 |
| Coverage measurement | BR-8, FR-11 |
| Evaluation harness | BR-10, FR-21 |
| Record/replay | NFR-3, FR-24 |

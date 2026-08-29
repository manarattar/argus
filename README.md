# ARGUS

**Agentic Risk Governance & Understanding System**

_From fragmented evidence to explainable risk intelligence._

ARGUS is a decision-support prototype for financial-risk analysts. It
investigates an organisation across a case file, extracts evidence it can prove
came from a source document, identifies risks, tests them against internal
policy, argues against its own conclusions, verifies that every claim is
actually carried by its citations, and computes an explainable provisional
rating — then stops, and hands the decision to a named human.

> **Independent portfolio demonstration.** Every document, policy and figure in
> this repository is synthetic and was written for this project. It is not
> affiliated with, derived from, or endorsed by any financial institution, and
> contains no real counterparty data.

---

## The one-paragraph version

Most LLM applications answer questions. This one produces a reviewable
artefact. The interesting engineering is not that a model reads documents — it
is everything built around the model so that its output can be trusted: quotes
re-verified against source text, citations enforced as identifiers rather than
prose, an adversarial agent whose job is to attack the findings, a rating
computed by arithmetic rather than generated as a label, and a workflow that
cannot complete without a recorded human decision.

---

## Contents

1. [The business problem](#the-business-problem)
2. [Why AI, and where not](#why-ai-and-where-not)
3. [What ARGUS does](#what-argus-does)
4. [The agentic workflow](#the-agentic-workflow)
5. [How it avoids making things up](#how-it-avoids-making-things-up)
6. [Human accountability](#human-accountability)
7. [Evaluation](#evaluation)
8. [Architecture](#architecture)
9. [Reusable platform design](#reusable-platform-design)
10. [Responsible AI](#responsible-ai)
11. [Security](#security)
12. [Business impact](#business-impact)
13. [Running it](#running-it)
14. [Demo Mode](#demo-mode)
15. [Testing](#testing)
16. [Tech stack](#tech-stack)
17. [Limitations](#limitations)
18. [Roadmap](#roadmap)

---

## The business problem

A risk analyst reviewing a corporate counterparty works from a file that is
fragmented by construction: an annual report, a financial summary, a governance
review, a supply-base assessment, a security assessment, relationship notes.
The judgement that matters usually sits in the *tension* between them — revenue
growing while margin compresses, a governance weakness with a credible but
unproven remediation, a supply-chain risk that is real but heavily mitigated.

The work is slow in specific, describable ways:

| Activity | Why it is slow |
|---|---|
| Finding the material statements | They are spread across hundreds of pages of mostly boilerplate |
| Relating findings to policy | Requires holding a framework of numbered thresholds in memory |
| Keeping counter-evidence in view | Confirmation bias is the default, and the file rarely volunteers it |
| Tracing a conclusion to its source | Needed for every review, painful to reconstruct afterwards |
| Recording what is missing | The absent document is the easiest thing to forget |
| Preparing the pack for a reviewer | Largely transcription, but must be exactly right |

None of that is a decision. All of it is preparation for one.

Full analysis: [`docs/business/problem-statement.md`](docs/business/problem-statement.md).

---

## Why AI, and where not

The design starts from a boundary rather than a capability.

**Language models are used for** the tasks where meaning has to be read out of
prose: interpreting a case file, lifting material statements, relating a finding
to a clause, constructing a counter-argument, drafting a narrative.

**Deterministic code is used for** anything that must be reproducible,
auditable, or resistant to a model's failure modes: quote verification,
cross-reference integrity, the uncertainty model, the risk score, escalation
rules, and every metric in the product.

**Humans decide.** Not as a policy statement — as a structural property. The
graph terminates at review, and no code path completes an assessment without a
recorded decision by a named person.

Asked directly for a rating, a language model produces a label that is unstable
across runs, sensitive to prompt phrasing, and impossible to reconcile with the
findings underneath it. So it is never asked. It supplies ordinal judgements it
is genuinely good at — how severe, how likely, what evidence bears on this —
and [`ai/scoring/engine.py`](ai/scoring/engine.py) combines them with arithmetic
a risk committee could audit on paper.

Full assessment, including the alternatives considered:
[`docs/business/ai-opportunity-assessment.md`](docs/business/ai-opportunity-assessment.md).

---

## What ARGUS does

A **case** is a review of one organisation. Opening it, an analyst can:

- **Run an investigation** — eight steps, observable as they execute, stopping
  at the review gate.
- **Read the assessment** — the rating with every factor that produced it, the
  narrative, the limitations, and what evidence would change the conclusion.
- **Inspect a finding** — supporting *and* contradicting evidence, each with a
  verbatim quote and a source locator; the verifier's verdict; the policy
  clauses it engages; its evidence-strength band and why.
- **Challenge it** — ask the Challenger agent for the strongest evidence-based
  case against any finding, on demand.
- **Override it** — change a severity or likelihood, or mark a false positive.
  A rationale is mandatory; the AI's original recommendation is never
  overwritten; the rating recomputes immediately and shows what moved.
- **Trace it** — the Evidence Graph draws lineage from rating to finding to
  evidence to document, and from finding to policy clause.
- **Model it** — the Scenario Lab varies a structured input the evidence
  actually contains and recomputes with the same engine.
- **Ask about it** — grounded Q&A over the case record, which refuses rather
  than speculates.
- **Decide** — approve, modify, request deeper investigation, escalate, or
  reject. Approval is blocked while a mandatory escalation stands.
- **Report it** — a structured assessment report, exportable as PDF.

---

## The agentic workflow

Implemented as a LangGraph state machine
([`ai/graphs/investigation.py`](ai/graphs/investigation.py)):

```
intake ─▶ extract ─┬─▶ risk ─▶ policy ─▶ challenge ─▶ verify ─┐
                   │                                          ▼
                   └────────────────────────────────────▶  score
                                                              │
                                                              ▼
                                                         synthesise
                                                              │
                                                              ▼
                                                  ■ HUMAN REVIEW GATE ■
```

| # | Agent | Responsibility | Output |
|---|---|---|---|
| 1 | **Intake & Planning** | Read the case, rank categories, record what is missing | `InvestigationPlan` |
| 2 | **Evidence Extraction** | Lift material statements with verbatim quotes | `EvidenceExtraction` |
| 3 | **Risk Specialist** | Identify risks the evidence supports | `RiskAnalysis` |
| 4 | **Policy Analyst** | Match findings to numbered clauses via RAG | `PolicyAnalysis` |
| 5 | **Challenger** | Argue *against* the findings | `ChallengeReport` |
| 6 | **Evidence Verifier** | Check citations actually carry each claim | `VerificationReport` |
| — | **Scoring & Integrity** | Deterministic. No model call. | rating + factors |
| 7 | **Risk Synthesis** | Explain the computed rating | `SynthesisNarrative` |
| 8 | **Report Generator** | Assemble the report from stored records | Markdown / PDF |

Three decisions worth asking about:

**Why a graph rather than a chain.** The workflow branches when extraction
yields nothing worth analysing, must survive a step failing without losing
completed work, and has to stop mid-flight and resume once a human has reviewed
it. A checkpointed state machine expresses all three; a chain of function calls
expresses none. ([ADR-001](docs/decisions/ADR-001-langgraph.md))

**Why the sequence is sequential.** Policy analysis and challenging could run
concurrently. They do not, because the gain is a couple of seconds and the cost
is a non-deterministic trace — and the trace is a product feature that analysts
and auditors read. A considered trade-off, not an omission.

**Why the gate is structural.** Stopping for review is not a UI convention a
caller could forget. The graph ends at `awaiting_human_review`; finalisation is
a separate entry point that cannot be reached without a recorded decision.
([ADR-003](docs/decisions/ADR-003-human-approval.md))

---

## How it avoids making things up

Four controls, none of which asks a model whether it was honest.

**1. Quote grounding.** Every extracted quote is re-matched against the stored
source chunk with plain string algorithms
([`ai/tools/grounding.py`](ai/tools/grounding.py)). Formatting drift passes;
paraphrase and invention do not. Evidence that cannot be located is discarded
before any other agent sees it — and *retained in the record as rejected*, so
the control is auditable rather than invisible.

**2. Cross-reference integrity.** Agents cite evidence by identifier, never by
sentence. Whether a citation resolves is therefore set membership, not
judgement ([`ai/graphs/integrity.py`](ai/graphs/integrity.py)). Unknown
identifiers are stripped and recorded. A finding left with no evidence is
*kept*, banded as Insufficient Evidence, and shown to the reviewer — more useful
than a finding that quietly disappears.

**3. Schema enforcement.** Every agent returns a validated Pydantic model. On
failure the validation error is fed back and the call retried; after the budget
the step fails visibly rather than degrading into prose
([`ai/providers/structured.py`](ai/providers/structured.py)).

**4. Evidence-weighted scoring.** A finding's inherent score is discounted by
its evidence band, so **weak evidence cannot produce a high rating**. That is
the anti-hallucination property expressed as arithmetic, and it is pinned by
tests (`tests/unit/test_scoring.py::test_weak_evidence_cannot_produce_a_high_rating`).

### Uncertainty without false precision

ARGUS never displays "94% confident". A model's stated confidence is not
calibrated, and presenting it as a probability invites the automation bias the
product exists to resist. Instead, evidence strength is computed from signals a
reviewer can dispute — corroborating citations, independent sources, grounding
quality, the verifier's verdict, contradictions, blocking information gaps — and
shown as **Strong / Moderate / Weak / Insufficient**, always with its reasoning
attached ([`ai/scoring/uncertainty.py`](ai/scoring/uncertainty.py)).

---

## Human accountability

- The investigation **stops** at review. There is no autonomous completion path.
- Every override stores **both** the AI recommendation and the human decision,
  with a mandatory rationale.
- The rating **recomputes** on the same engine after an edit, so the analyst
  sees the consequence explained rather than a number that silently changed.
- **Approval is blocked** while a domain escalation rule stands. The analyst can
  escalate or reject; they cannot approve past a control.
- The **override rate** is a first-class metric on the AI Operations page. Near
  zero suggests rubber-stamping; very high suggests the model is not earning its
  place. Both are failure modes, and neither is visible unless you store the
  original.
- The **audit trail** is append-only by construction: one write function, and no
  code anywhere that can update or delete an entry.

---

## Evaluation

`make eval`, or the in-app Evaluation Lab. The suite splits deliberately:

- **45 deterministic cases** — retrieval ranking, quote grounding (including
  negative cases that *must* be rejected), the scoring engine, the uncertainty
  model, escalation rules, the prompt trust boundary, citation integrity. These
  need no model and run identically on any clone.
- **8 model-dependent cases** — structured-output conformance, contradiction
  detection, and three prompt-injection cases. These need a live backend or
  recordings, and are reported as **skipped — never as passed** — when neither
  is available.

Two figures are always shown together: **pass rate** over executed cases, and
**coverage** — how much of the suite actually ran. A run that skipped most of
its cases cannot present itself as a strong result.

Current result on a clone with no API key:

```
TOTAL                  45/45 pass    100%   (8 skipped, 0 errored)
suite coverage         85% of cases executed
```

The suite has already earned its place: it caught a mis-calibration where a
severe, well-evidenced finding could not reach a High rating — contradicting the
scoring engine's own documented design. The engine was fixed, not the test.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Next.js analyst workspace                               │
│  case investigation · evidence graph · review · lab      │
└───────────────────────────┬──────────────────────────────┘
                            │ typed HTTP
┌───────────────────────────▼──────────────────────────────┐
│  FastAPI · validation · serialisation · audit trail      │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│  LangGraph orchestration                                 │
│  routing · per-step failure handling · human gate        │
└─────────┬───────────────────────────────┬────────────────┘
          │                               │
┌─────────▼─────────────┐    ┌────────────▼─────────────────┐
│ Reusable capabilities │    │ Deterministic controls       │
│ plan · extract · risk │    │ grounding · integrity        │
│ policy · challenge    │    │ uncertainty · scoring        │
│ verify · synthesise   │    │ escalation                   │
│ (model calls)         │    │ (no model calls)             │
└─────────┬─────────────┘    └────────────┬─────────────────┘
          └───────────────┬───────────────┘
┌───────────────────────────▼──────────────────────────────┐
│  Retrieval + storage                                     │
│  structure-aware chunking · hybrid BM25 + vector         │
│  SQLite (default) or PostgreSQL + pgvector               │
└───────────────────────────┬──────────────────────────────┘
┌───────────────────────────▼──────────────────────────────┐
│  Observability + evaluation                              │
│  step traces · tokens · cost · overrides · eval runs     │
└──────────────────────────────────────────────────────────┘
```

The in-app **Architecture** page renders this from the running system —
capabilities, domains, prompt versions and controls are read from the modules
that define them, so it cannot drift from the code.

Details: [`docs/architecture/overview.md`](docs/architecture/overview.md).

### Repository map

```
argus/
├─ ai/                        the AI layer — no web or database code
│  ├─ agents/                 seven investigation agents, as plain functions
│  ├─ graphs/                 LangGraph state machine + integrity controls
│  ├─ prompts/library.py      versioned prompts + the untrusted-content boundary
│  ├─ providers/              model abstraction, structured output, record/replay
│  ├─ retrieval/              chunking, embeddings, hybrid search
│  ├─ scoring/                deterministic engine, uncertainty, coverage
│  ├─ schemas/                Pydantic contracts for every agent boundary
│  ├─ evaluators/             evaluation harness and checks
│  └─ domain.py               domain configuration — the platform seam
├─ apps/
│  ├─ api/                    FastAPI: routers, services, ORM
│  └─ web/                    Next.js analyst workspace
├─ data/
│  ├─ demo/northstar/         six synthetic case documents
│  ├─ policies/               four fictional policy standards (CRF/FRS/GOS/TRA)
│  ├─ evals/cases.jsonl       53 evaluation cases
│  └─ recordings/             captured model responses for Demo Mode
├─ docs/                      business, architecture, responsible AI, ADRs
├─ tests/                     unit, integration, agent tests
└─ scripts/                   seed, evaluate, record, doctor
```

---

## Reusable platform design

The agents, retrieval, grounding, scoring, review workflow and evaluation
harness contain **no counterparty-review logic**. Everything domain-specific —
risk categories, expected evidence, policy library, escalation thresholds —
lives in a `DomainConfig` value ([`ai/domain.py`](ai/domain.py)).

Adding a review type is a configuration plus a policy library, not a fork of the
pipeline. That claim is only credible if the seam is visible, so the registry
deliberately carries three **design-stage** domains (KYC, Vendor Risk,
Compliance Review) marked `status="design"`. The API exposes them and the
Architecture page renders them — labelled as scoped, not built. Only
Counterparty Risk has a corpus, recordings and evaluation behind it.

---

## Responsible AI

[`docs/responsible-ai/model-risk.md`](docs/responsible-ai/model-risk.md) works
through thirteen risks — hallucination, automation bias, prompt injection,
retrieval error, drift, bias, provider dependency and others — each with impact,
mitigation, **residual risk**, and how it is tested.

Several controls are visible in the product itself: rejected evidence is shown
rather than hidden, unresolved challenges are surfaced, information gaps appear
as limitations on the report, and the operating mode is stated permanently in
the UI chrome.

### Prompt injection

Case documents are untrusted — in a real deployment they may be drafted by the
counterparty. Every piece of retrieved content is wrapped in a labelled block
and each system prompt states that content inside those blocks is evidence to
analyse, never instruction to follow
([`ai/prompts/library.py`](ai/prompts/library.py)).

That is a mitigation, not a guarantee, which is why it is paired with controls
that do not depend on the model complying — grounding, integrity checks,
deterministic scoring — and with evaluation cases where a document instructs the
model to assign a low rating, reveal its instructions, or suppress a category.
Three structural cases (boundary enforcement) run everywhere; three behavioural
cases need a model.

---

## Security

Appropriate for a prototype, and honest about it: CORS restricted by
configuration, security headers set, request bodies bounded, upload types
constrained, opaque error responses with a traceable request id, no secrets in
the repository, parameterised queries throughout.

**Authentication is deliberately absent.**
[`docs/architecture/security.md`](docs/architecture/security.md) records exactly
what would need to change before this ran anywhere real — identity, tenancy,
encryption, retention, secret management, egress control.

---

## Business impact

The **Value Case** page models the business case over assumptions you can
change. It is deliberately conservative in three ways:

1. The saving applies to **preparation time only** — review, judgement and
   sign-off are unchanged, because the product does not remove them.
2. Saved hours are **capacity released**, not cost removed. Nobody leaves a team
   because a tool got faster.
3. The benefit is scaled by an **adoption rate**, because a tool nobody uses
   saves nothing.

Sensitivity analysis shows which assumption the conclusion actually depends on.
Every figure is labelled illustrative and is not measured from a production
deployment.

---

## Running it

### Requirements

Python 3.11+, Node 20+. Docker optional. **No API key required.**

### Fastest path

```bash
git clone <repository-url> argus
cd argus

make setup        # virtualenv, backend + frontend dependencies, .env
make seed         # ingest the synthetic corpus and policy library
make dev          # API on :8000, web on :3000
```

Open <http://localhost:3000>.

To also run the investigation graph during seeding:

```bash
make seed-full
```

### With live inference

```bash
cp .env.example .env
# set OPENAI_API_KEY (or ANTHROPIC_API_KEY)
make seed-full    # re-seed: a real embedding backend rebuilds the index
```

Confirm what is actually running — without printing any secret:

```bash
make doctor
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Brings up PostgreSQL with pgvector, the API and the web app. The same code path
runs; only `DATABASE_URL` changes.

### Useful targets

| Command | Does |
|---|---|
| `make seed` / `make seed-full` | Load the corpus, optionally investigate |
| `make dev` | Run API and web together |
| `make test` | Full Python test suite |
| `make eval` | Evaluation suite with a per-category breakdown |
| `make lint` | Ruff, mypy, ESLint, tsc |
| `make doctor` | Report the resolved runtime configuration |
| `make check` | Everything CI runs |

---

## Demo Mode

A portfolio project has two audiences with incompatible needs. A recruiter
should see the product work in sixty seconds with no account and no spend. An
engineer should be able to confirm the agents are real.

Shipping pre-written answers would fail the second audience — and the failure
would be exactly what this project argues against. So ARGUS records real model
exchanges and replays them, keyed by a hash of the exact prompt
([`ai/providers/replay.py`](ai/providers/replay.py)).

|                | Demo Mode | Live |
|---|---|---|
| Text generation | Replayed from recordings | Live model call |
| Model, tokens, latency shown | From the original capture | From the call |
| Chunking, retrieval, grounding | **Executes** | Executes |
| Schema validation, integrity | **Executes** | Executes |
| Scoring, uncertainty, escalation | **Executes** | Executes |
| Evaluation harness | **Executes** | Executes |

A replayed response that cites evidence which does not exist is rejected by the
same controls that would reject it live. A cache miss raises — it never
substitutes content of its own — and the UI shows the real error.

The mode is stated permanently in the sidebar, on every investigation, and
against every evaluation run.

---

## Testing

```bash
make test          # 95 tests: unit + integration
make eval          # evaluation suite
make e2e           # Playwright end-to-end (requires a running stack)
```

| Layer | Covers |
|---|---|
| **Unit** | Scoring arithmetic, grounding accept/reject, uncertainty bands, coverage, escalation, domain config, value model |
| **Integration** | The full graph over the real corpus with a scripted backend; grounding rejecting a planted fabrication; citation stripping; override + rescore; escalation blocking approval; failure handling |
| **API** | Status codes, validation, error shapes, security headers, honest evaluation metrics |
| **E2E** | Navigation, review gate, finding → evidence trace, override validation, report, evidence graph |

The integration suite is the one that matters most: it plants a fabricated quote
in the scripted extractor output and asserts the pipeline rejects it, and cites
evidence that does not exist and asserts it is stripped. Coverage is not
claimed as a percentage — what is tested is listed above.

---

## Tech stack

**Backend** Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 · LangGraph ·
SQLite / PostgreSQL + pgvector · ReportLab

**Frontend** Next.js 14 (App Router) · TypeScript (strict) · Tailwind ·
hand-built component system · inline SVG for the evidence graph

**Quality** pytest · Ruff · mypy · ESLint · Playwright · Docker Compose

---

## Limitations

Stated plainly, because a portfolio project that hides them is less credible,
not more.

- **The corpus is synthetic.** Northstar is invented. Real filings are messier,
  longer, and worse structured, and would need OCR and table extraction.
- **Without an API key, retrieval is lexical.** The fallback vectoriser matches
  term overlap, not meaning: it does not know "gearing" and "leverage" are
  related. Stated in the UI and in evaluation results.
- **Investigations run synchronously.** Fine at seconds; a production deployment
  needs a job queue and streaming.
- **No authentication.** Deliberate for a prototype; documented.
- **Prompt-injection defence is partial.** Prompt-level boundaries reduce the
  surface; the architecture contains it. Neither is a guarantee.
- **Scoring thresholds are calibrated against one corpus.** They are policy
  parameters a risk function would own and tune against real outcomes.
- **The Challenger has no memory across runs.** It re-derives challenges each
  time rather than tracking which were resolved previously.
- **Scenario Lab is narrow by design.** Declared structured variables only. It
  cannot model an arbitrary "what if", and does not pretend to.

---

## Roadmap

Ordered by value, not novelty.

1. **Retrieval quality** — rerank the fused candidate set; measure against the
   existing suite rather than assuming improvement.
2. **Asynchronous investigations** — job queue plus streamed step updates.
3. **Calibration** — track override rates by category and feed them back into
   the scoring parameters, so the engine learns from analyst disagreement.
4. **Second domain** — implement Vendor Risk end to end. That is the honest test
   of the platform claim.
5. **Document ingestion** — PDF and table extraction, so real filings work.
6. **Reviewer view** — a senior-reviewer surface built around overrides and
   unresolved challenges rather than around findings.
7. **Enterprise hardening** — identity, tenancy, retention, secret management.

---

## Licence

MIT — see [LICENSE](LICENSE).

Built by Manar Attar as an independent demonstration of applied AI product and
engineering practice.

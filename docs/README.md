# Documentation

Start with the [project README](../README.md). This index is for going deeper.

## Business

| Document | Answers |
|---|---|
| [Problem statement](business/problem-statement.md) | What is slow about counterparty review, and why |
| [Stakeholders](business/stakeholders.md) | Who the users are, and which design decision each one forced |
| [Requirements](business/requirements.md) | What was built, and the traceability matrix connecting it to the business case |
| [AI opportunity assessment](business/ai-opportunity-assessment.md) | Where AI belongs, where it does not, and the five alternatives rejected |

## Architecture

| Document | Answers |
|---|---|
| [Overview](architecture/overview.md) | Layers, lifecycle, failure handling, and where the seams are |
| [Scoring and uncertainty](architecture/scoring.md) | Exactly how the rating and evidence bands are computed |
| [Data model](architecture/data.md) | What is stored, what is deliberately not, and why |
| [Security](architecture/security.md) | What is implemented, and what a production deployment would need |

## Decisions

Architecture Decision Records, each with the alternatives considered and the
consequences accepted.

| ADR | Decision |
|---|---|
| [ADR-001](decisions/ADR-001-langgraph.md) | Orchestrate as a LangGraph state machine |
| [ADR-002](decisions/ADR-002-evidence-first.md) | Evidence-first, with a computed rating |
| [ADR-003](decisions/ADR-003-human-approval.md) | Human approval is structural, not procedural |
| [ADR-004](decisions/ADR-004-domain-configuration.md) | Domain logic lives in configuration |
| [ADR-005](decisions/ADR-005-storage-and-retrieval.md) | SQLite by default, Postgres + pgvector deployed |
| [ADR-006](decisions/ADR-006-provider-abstraction.md) | One model interface, with record and replay |

## Responsible AI

| Document | Answers |
|---|---|
| [Model risk assessment](responsible-ai/model-risk.md) | Thirteen risks with impact, mitigation, **residual risk** and testing approach |

The residual-risk column is the point. Three items are genuinely open: bias
(unassessed), production data privacy (documented, not mitigated), and
automation bias (an operational control, not a technical one).

## Portfolio

| Document | Answers |
|---|---|
| [Interview story](portfolio/interview-story.md) | How to explain this in 30 seconds, 2 minutes or 5 — and the questions to expect |
| [Demo script](portfolio/demo-script.md) | A timed walkthrough that tells one coherent story |

## Reading paths

**Recruiter, 5 minutes.** README hero section → [demo script](portfolio/demo-script.md).

**Hiring manager, 20 minutes.** README → [problem statement](business/problem-statement.md)
→ [AI opportunity assessment](business/ai-opportunity-assessment.md)
→ [requirements traceability matrix](business/requirements.md#6-requirements-traceability-matrix).

**Engineer, 30 minutes.** [Architecture overview](architecture/overview.md) →
[ADR-002](decisions/ADR-002-evidence-first.md) → `ai/graphs/investigation.py` →
`ai/scoring/engine.py` → `tests/integration/test_investigation_flow.py`.

**Risk or compliance reviewer.**
[Model risk assessment](responsible-ai/model-risk.md) →
[ADR-003](decisions/ADR-003-human-approval.md) →
[security](architecture/security.md).

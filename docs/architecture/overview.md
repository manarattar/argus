# Architecture Overview

## Layers

```
Next.js workspace      analyst UI; no business logic
        │  typed HTTP
FastAPI service        validation, serialisation, audit trail; no model logic
        │
LangGraph graph        routing, per-step failure handling, human gate
        │
   ┌────┴────────────────────────┐
Capabilities              Controls
(model calls)             (no model calls)
plan, extract, risk,      grounding, integrity,
policy, challenge,        uncertainty, scoring,
verify, synthesise        coverage, escalation
   └────┬────────────────────────┘
        │
Retrieval + storage    chunking, hybrid search, SQLite or Postgres+pgvector
        │
Observability          step traces, tokens, cost, overrides, evaluation
```

The dependency rule is one-directional and strictly enforced by where code
lives: `ai/` imports nothing from `apps/`. The AI layer has no idea a database
or a web server exists, which is why every agent is callable from a test or an
evaluation case without standing anything up.

## Module responsibilities

| Module | Responsibility | Must not |
|---|---|---|
| `ai/schemas/` | Typed contracts at every agent boundary | Contain logic |
| `ai/prompts/` | Versioned prompts, trust boundary | Contain domain data |
| `ai/providers/` | Model abstraction, structured output, record/replay | Leak vendor types outward |
| `ai/retrieval/` | Chunking, embeddings, hybrid search | Know about cases |
| `ai/agents/` | Seven agents as plain functions | Hold state or call each other |
| `ai/graphs/` | Sequencing, failure handling, integrity | Contain prompt text |
| `ai/scoring/` | Rating, uncertainty, coverage, escalation | Call a model |
| `ai/domain.py` | All domain-specific configuration | — |
| `ai/evaluators/` | Harness and checks | Depend on a live model for deterministic cases |
| `apps/api/.../services/` | Orchestration, persistence, audit | Contain prompt text |
| `apps/api/.../routers/` | HTTP surface | Contain business logic |
| `apps/web/` | Presentation | Compute a rating or reinterpret a result |

## Investigation lifecycle

1. **Ingest** — documents chunked on their heading structure, each chunk carrying
   a deterministic citation key. Embedded once, at ingest.
2. **Plan** — the planner reads case metadata and the document inventory,
   ranks categories, and records gaps against what the domain says a complete
   file contains.
3. **Extract** — retrieval runs per priority category; the extractor returns
   evidence with verbatim quotes.
4. **Ground** — every quote is re-verified against stored chunk text. Failures
   are dropped and recorded; wrong-chunk references are repaired.
5. **Analyse** — risks cite surviving evidence by identifier.
6. **Policy** — findings drive retrieval over the policy library; matches carry a
   clause reference and relationship type.
7. **Challenge** — the Challenger receives the *complete* evidence set, including
   items the risk agent did not cite, because overlooked evidence is often the
   strongest basis for a challenge.
8. **Verify** — each finding is checked against its citations.
9. **Score** — deterministic. Integrity enforcement, evidence-strength grading,
   coverage, the composite rating and escalation rules. No model call.
10. **Synthesise** — the narrative is written *around* the already-computed
    rating, which is supplied to the agent as context it must explain rather than
    decide.
11. **Stop** — status becomes `awaiting_human_review`. The graph has no edge
    beyond this point.

## Why the deterministic step sits between the agents and the narrative

This ordering is the architectural expression of the product principle. Scoring
runs *before* synthesis, so the narrative agent is given the rating and told to
explain it. If synthesis ran first and scoring second, the narrative could
contradict the number. If synthesis produced the rating, none of the properties
in ADR-002 would hold.

A consequence worth noting: when synthesis fails, the rating still stands,
because it was computed independently. The UI reports the missing narrative
rather than covering for it.

## Failure handling

| Failure | Behaviour |
|---|---|
| Planning fails | Run halts; recorded as failed |
| Extraction fails | Run halts — nothing to analyse, score or narrate |
| Extraction yields < 2 grounded items | Skips analysis, proceeds to scoring; reports honestly |
| Policy / challenge / verify fails | Step recorded as failed; remaining steps continue |
| Synthesis fails | Rating stands; narrative absent and reported as absent |
| Schema invalid | Retry with the error fed back; visible failure after budget |
| Replay cache miss | Raises; surfaces as a failed step with the real reason |

Nothing is ever substituted for missing model output.

## Synchronous execution

Investigations run synchronously in the request. At the scale of a six-document
case this takes seconds, and a job queue plus polling would add moving parts
without changing anything the product demonstrates.

A production deployment would move this to a worker with streamed step updates.
The seam already exists: `InvestigationRunner` accepts an `on_step` callback that
currently drives nothing, and would drive a stream.

## Data model notes

Agent output is persisted as first-class rows with real foreign keys, not JSON
blobs. That is what makes the Evidence Graph a query rather than a parsing
exercise, and what lets the audit trail reference a specific finding.

Human overrides are stored *beside* the AI recommendation, never instead of it.
Losing the original would destroy the only measurement of how often the system
is wrong.

The audit table has exactly one write path and no update or delete code anywhere
in the application. Immutability is a property of the code, not a convention.

## Frontend

Server Components fetch uncached, so the dashboard always reflects the current
database. Client Components handle interaction: the investigation workspace holds
the investigation in one place, because a single edit changes the rating, the
factors and the escalation state at once.

The component system is hand-built rather than imported. The set needed is small
and specific, and an enterprise analytics interface depends on density and
restraint — qualities easier to hold when the primitives are yours.

## Where the seams are

If you want to change one thing, this is where it lives:

| Change | Touch |
|---|---|
| Model provider | `.env`, `MODEL_BACKEND` |
| Prompt wording | `ai/prompts/library.py`, bump the version |
| Scoring weights | `ai/scoring/engine.py` constants |
| Risk taxonomy | `ai/schemas/enums.py` + `ai/domain.py` |
| New review type | `ai/domain.py` + a policy corpus |
| Evidence-strength rules | `ai/scoring/uncertainty.py` |
| Escalation rules | `ai/domain.py` |
| Evaluation cases | `data/evals/cases.jsonl` |

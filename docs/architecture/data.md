# Data Model

## Design principles

**Agent output is persisted as first-class rows.** Evidence, findings, policy
matches, challenges and verifications each get a table with real foreign keys.
That is what makes the Evidence Graph a join rather than a parsing exercise, and
what lets an audit entry reference a specific finding.

**Both sides of a disagreement are kept.** A `risks` row carries `ai_severity`
and `severity`. The first never changes; the second is what the analyst decided.
Losing the original would destroy the only measurement of how often the system
is wrong.

**The audit trail is append-only by construction.** One write function
(`services/audit.py::record`), and no update or delete code anywhere in the
application. See [`security.md`](security.md) for what database-level
enforcement would add.

**Embeddings are stored portably.** JSON on SQLite, a `vector` column on
Postgres. The retrieval interface is identical, so the storage choice never
leaks into agent code.

## Tables

| Table | Holds | Notes |
|---|---|---|
| `cases` | The subject under review | `domain_key` selects the configuration |
| `documents` | Source text | `doc_kind` separates case from policy |
| `chunks` | Retrievable units | Citation key, section, page, embedding |
| `investigations` | One graph execution | Rating, factors, coverage, narrative, cost, integrity report |
| `investigation_steps` | One node execution | Status, summary, prompt reference, tokens, cost, error |
| `evidence` | Grounded evidence | Quote, source locator, grounding score |
| `risks` | Findings | AI values and current values side by side |
| `policy_matches` | Clause links | Deterministic clause reference |
| `challenges` | Adversarial arguments | `on_demand` distinguishes analyst-requested |
| `verifications` | Claim verdicts | Four-valued status |
| `overrides` | Human changes | AI value, human value, mandatory rationale, actor |
| `reviews` | The decision | AI rating and final rating both recorded |
| `audit_events` | Everything that happened | Append-only; before/after payloads |
| `eval_runs` / `eval_results` | Evaluation history | Backend and model recorded per run |

## Identifiers

Case-scoped identifiers minted by agents (`E1`, `R2`) are namespaced on
persistence as `{investigation_id}:{agent_id}`. Agents can therefore use short,
readable identifiers in prompts while rows stay globally unique.

Chunk ids are `{document_id}::c{ordinal}` — deterministic, so re-ingesting the
same document produces the same ids and existing citations continue to resolve.

## Rejected evidence

Stored as JSON on the investigation rather than in the `evidence` table, because
it is deliberately *not* evidence: it must never be joinable as though it were.
Retaining it makes the grounding control auditable, and lets the operations page
report how often the control actually fires.

## What is not stored

**Model reasoning.** Chain-of-thought is not requested, not returned in traces,
and not persisted. Step detail carries structured facts about the step —
retrieval counts, attempts, integrity outcomes — and nothing else.

**Raw prompts.** Prompts are reconstructible from the versioned library plus the
stored inputs, so storing them again would duplicate case content for no benefit.
Recordings do contain prompt hashes, not prompt text.

## Retention

Not implemented. Case documents, prompts, recordings and audit entries currently
persist indefinitely. Required policy is documented in
[`security.md`](security.md).

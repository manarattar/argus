# ADR-002 — Evidence-first architecture, with a computed rating

**Status** Accepted · **Date** 2026-08 · **Decides** how conclusions relate to evidence

## Context

The central risk in applying a language model to risk assessment is not that it
writes badly. It is that it writes *plausibly* about things that are not in the
document, and that a reader cannot tell the difference.

Two design questions follow. How do we know a citation is real? And who decides
the rating?

## Decision

**Evidence is the primary artefact.** Nothing downstream may assert anything not
anchored to an evidence identifier. Agents cite by identifier, never by sentence,
so citation validity becomes set membership rather than judgement.

**Every quote is re-verified against stored source text.** Extraction proposes;
`ai/tools/grounding.py` disposes. Unverifiable evidence never reaches the risk
agent, and is retained in the record as rejected so the control is auditable.

**The rating is computed, not generated.** The model supplies ordinal judgements
— severity, likelihood, what evidence bears on what. `ai/scoring/engine.py`
combines them into a 0–100 composite via named factors.

## Why not let the model produce the rating

It is the obvious approach, and it fails on four properties the domain requires:

| Property | Model-generated | Computed |
|---|---|---|
| Reproducibility | Varies across runs and phrasings | Identical inputs, identical output |
| Explainability | "Because the risks are significant" | Every point attributable to a named factor |
| Testability | Only end-to-end, weakly | Ordinary unit tests |
| Governability | Change by re-prompting and hoping | Thresholds are parameters a risk function owns |

The model shapes the inputs; the institution owns the function.

## Consequence: weak evidence cannot produce a high rating

Because a finding's inherent score is discounted by its evidence band, a
fabricated or unsupported finding cannot drive the assessment even if the model
states it with total confidence. This is the anti-hallucination property
expressed as arithmetic rather than as a prompt instruction, and it is pinned by
`tests/unit/test_scoring.py`.

## Alternatives considered

**Trust the model's citations.** Cheapest, and defeats the purpose.

**Verify with a second model.** Better than nothing, but circular: the check
shares the failure modes of the thing being checked, and cannot be tested
deterministically.

**Embedding similarity between quote and source.** Tolerant in the wrong
direction. A paraphrase scores highly, and a paraphrase is exactly what must be
rejected when a verbatim quote was requested.

**Model-generated rating with a deterministic sanity check.** Considered
seriously. Rejected because it produces two numbers that can disagree, with no
principled way to reconcile them in front of a user.

## Consequences

**Positive.** "No fabricated citations" becomes a testable property. Ratings are
reproducible and explainable. Scoring is unit-testable without a model. Weak
evidence is structurally incapable of driving a rating.

**Negative.** Extraction must produce verbatim quotes, which constrains the
prompt and occasionally costs a genuine finding whose quote drifted. Mitigated by
recovering evidence whose quote matches a *different* chunk than the one cited —
real evidence with a wrong pointer is corrected rather than discarded. Scoring
weights become a calibration burden the institution owns; the evaluation suite
exists partly to make that burden manageable.

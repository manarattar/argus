# ADR-004 — Domain logic lives in configuration, not in code

**Status** Accepted · **Date** 2026-08 · **Decides** how the platform extends

## Context

Counterparty review is one of several assessment workflows an institution runs.
KYC onboarding, vendor risk and compliance review share the same shape — gather
evidence, identify risks, test against policy, challenge, verify, review — while
differing in risk taxonomy, expected evidence, policy library and escalation
thresholds.

Building for counterparty review alone is faster. Building a platform that only
ever serves one domain is worse than either.

## Decision

Everything domain-specific lives in a `DomainConfig` value in `ai/domain.py`:

- risk categories in scope;
- expected evidence categories, used to measure completeness;
- policy library;
- escalation rules;
- review objective and subject noun.

The agents, retrieval, grounding, scoring, review workflow, audit trail and
evaluation harness contain **no counterparty-review logic**. Agents receive the
domain through their context and read categories and expectations from it.

Adding a review type is therefore a configuration value plus a policy corpus.

## Making the claim falsifiable

A platform claim nobody can check is marketing. Two things make this one
checkable:

**The seam is visible.** The registry carries three design-stage domains marked
`status="design"`. The API exposes them and the Architecture page renders them —
clearly labelled as scoped, not built. Anyone can read `ai/domain.py` and see
exactly what a new domain would have to supply.

**It is stated honestly.** Only counterparty review has a corpus, recordings and
evaluation behind it. The UI says "design only" on the others rather than
implying four working domains. A test asserts exactly one domain reports as
implemented.

## Alternatives considered

**Hardcode counterparty review; generalise later.** Faster now. In practice
"later" means a rewrite, because domain assumptions leak into prompts, schemas
and scoring in ways that are hard to untangle once written.

**A plugin architecture with per-domain code modules.** More flexible, and more
than the problem needs. Every domain examined differs in *data*, not in
*algorithm*. A plugin system would add indirection with no current use.

**Ship four half-built domains.** Rejected outright. It would make the platform
claim look stronger and be materially dishonest — the exact failure mode this
project argues against elsewhere.

## Consequences

**Positive.** The reusable/domain boundary is explicit and enforced by where code
lives. A new review type is a small, reviewable change. The Architecture page can
render domains from configuration because that is genuinely where they live.

**Negative.** One indirection between agents and their categories. The claim
remains partly unproven until a second domain is implemented end to end — which
is why it sits near the top of the roadmap rather than being asserted as done.

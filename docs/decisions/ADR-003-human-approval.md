# ADR-003 — Human approval is structural, not procedural

**Status** Accepted · **Date** 2026-08 · **Decides** how the workflow terminates

## Context

"A human reviews the output" is the most commonly stated and least commonly
enforced control in enterprise AI. It usually means a screen exists with an
Approve button, which a user under time pressure clicks.

Three failure modes matter:

1. **Bypass.** Some caller — a batch job, an integration, a future feature —
   completes an assessment without review.
2. **Rubber-stamping.** Review happens but adds nothing, and nobody can tell.
3. **Approval past a control.** An analyst approves something a policy rule says
   must be escalated.

## Decision

**The graph terminates at review.** `ai/graphs/investigation.py` ends at
`awaiting_human_review`. There is no edge to a completed state. Finalisation is a
separate entry point (`services/review.py::submit_review`) reachable only with a
recorded decision, actor and timestamp.

**Overrides store both values.** The AI recommendation is never overwritten. A
rationale is mandatory, enforced in the service layer rather than only in the
form.

**Escalation blocks approval.** When a domain escalation rule fires, `approve` is
refused at the service layer and disabled in the UI. The analyst may escalate or
reject; they cannot approve past a control.

**The override rate is a headline metric.** Near zero suggests rubber-stamping;
very high suggests the model is not earning its place. Both are documented as
failure modes on the AI Operations page.

## Alternatives considered

**A UI-only gate.** The default, and it addresses none of the three failure
modes. Any new caller bypasses it.

**Approval with an optional comment.** Cheaper for the analyst, and produces an
audit trail recording *that* someone approved without recording *why* — close to
worthless in a review.

**Auto-approve below a risk threshold.** Superficially reasonable. Rejected
because the cases where the model is most wrong are not reliably the cases it
rates as high risk. A confidently-wrong Low is precisely the failure this control
exists to catch.

**Allow approval with an override for escalations.** Rejected. A control that can
be waived by the person it constrains is not a control. Escalation to a more
senior reviewer is the correct release valve, and it exists.

## Consequences

**Positive.** No code path completes an assessment without human accountability.
Divergence is measurable. Escalation rules are enforced rather than advisory. The
audit trail answers "who decided this, and why".

**Negative.** Every assessment requires a human action, so the system cannot
process a backlog unattended. This is intended. Mandatory rationales add friction
to overrides — also intended, since an unexplained override is not reviewable.

**Tested by** `tests/integration/test_investigation_flow.py::TestHumanReview`,
covering the terminal state, override recording, rescoring, refusal without
rationale, and refusal of approval while an escalation stands.

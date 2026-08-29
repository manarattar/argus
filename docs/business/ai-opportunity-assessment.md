# AI Opportunity Assessment

> Fictional assessment written for the ARGUS demonstration.

The purpose of this document is to be specific about where AI belongs in this
workflow and — more importantly — where it does not. A design that applies a
language model to every step would be easier to build and considerably worse.

---

## 1. Decomposing the workflow

Each step of the current-state workflow, classified by what it actually requires.

| Step | Nature of the work | Right tool | Why |
|---|---|---|---|
| Assemble the file | Retrieval, collation | Conventional software | Deterministic, no interpretation |
| Locate material statements | Reading comprehension over prose | **LLM** | Materiality is contextual and cannot be specified as rules |
| Verify a quote is real | Exact matching | **Deterministic code** | Verifiable; must not depend on the thing being verified |
| Normalise a statement | Language transformation | **LLM** | Restating faithfully is a language task |
| Distinguish fact from inference | Judgement about epistemic status | **LLM**, schema-enforced | Requires reading; the schema forces the distinction |
| Assign severity / likelihood | Calibrated ordinal judgement | **LLM**, human-adjustable | Models are reasonable at ordinals, unreliable at absolutes |
| Combine findings into a rating | Aggregation | **Deterministic code** | Must be reproducible, explainable and governable |
| Locate the applicable clause | Semantic matching over a corpus | **Retrieval + LLM** | Wording differs; meaning does not |
| Decide a threshold is crossed | Numeric comparison | **Deterministic code** | 62% > 50% is arithmetic, not judgement |
| Construct the counter-case | Adversarial reasoning | **LLM** | Genuinely hard for a person with a formed view |
| Check a claim against citations | Comparative reading | **LLM**, second pass | Different task from producing the claim |
| Check a citation resolves | Set membership | **Deterministic code** | Trivially verifiable; must never be judged |
| Measure completeness | Comparison against a specification | **Deterministic code** | The specification is domain configuration |
| Decide escalation | Rule application | **Deterministic code** | A control must not depend on model compliance |
| Draft the narrative | Writing | **LLM** | Language task, bounded by computed inputs |
| Approve the assessment | Accountable decision | **Human** | Institutional and regulatory requirement |

Roughly half the workflow is deliberately *not* an AI problem.

---

## 2. Where AI is genuinely appropriate

**Reading comprehension at scale.** Identifying the thirty material sentences in
two hundred pages is exactly what language models are good at and exactly what
is expensive in analyst time.

**Semantic matching against policy.** A finding about "62% of revenue from two
customers" must reach a clause about "customer concentration" that never uses
those words. Retrieval plus interpretation handles this; keyword rules do not.

**Adversarial reasoning.** This is the strongest case in the whole workflow. A
model has no investment in the conclusion, does not tire, and will argue against
a finding as readily as for it. For a human, actively attacking their own
analysis is cognitively expensive and inconsistently done. The Challenger agent
does something people are structurally bad at.

**Second-pass verification.** Checking whether a claim is carried by its
citations is a different task from producing the claim, and a fresh pass with no
stake in the original catches overstatement — the "significant deterioration"
versus "modest decline" gap.

**Bounded drafting.** Writing a summary of already-computed results is a
language task with no discretion over the conclusions.

---

## 3. Where deterministic software is better

**Anything that verifies the model.** Grounding and citation integrity must not
depend on a model, or the control is circular. String matching and set
membership are cheap, exact and unarguable.

**The rating.** Discussed at length in [ADR-002](../decisions/ADR-002-evidence-first.md)
and the scoring notes. Computing it buys reproducibility, explainability,
testability and governability. Generating it buys none of them.

**Threshold comparisons.** Once a figure is extracted, comparing it to a policy
limit is arithmetic. Asking a model to do arithmetic introduces error for no
benefit.

**Escalation.** A control that depends on a model choosing to honour it is not a
control. Escalation rules are domain data evaluated in code.

**Every metric in the product.** Override rates, coverage, cost, evaluation
results. A metric produced by a model is not a measurement.

---

## 4. Where human judgement is irreducible

**The decision.** Not a technical limitation. The institution is accountable,
and accountability cannot be delegated to a system that cannot be held to
account.

**Materiality in context.** The model can identify that debt doubled. Whether
that matters *for this counterparty, this exposure, this relationship* depends on
knowledge the file does not contain.

**Weighing incommensurables.** Governance weakness against a credible
remediation, concentration against a long relationship. Reasonable analysts
disagree; that disagreement is the value of the review.

**Deciding what "enough evidence" means.** The system reports evidence strength.
Whether Moderate is sufficient for *this decision* is a risk-appetite question
owned by the institution.

---

## 5. Risks of using AI here

| Risk | Why it matters in this domain | Design response |
|---|---|---|
| **Hallucinated evidence** | A fabricated quote in a risk assessment is a serious failure | Deterministic grounding; rejects retained and shown |
| **Automation bias** | An analyst accepting a confident summary is the primary failure mode | Counter-evidence shown alongside; no confidence percentages; override rate measured |
| **False precision** | "94% confident" invites unearned trust | Interpretable bands with rationale |
| **Confirmation amplification** | A model can rationalise a finding as fluently as justify it | Dedicated adversarial agent; verifier second pass |
| **Prompt injection** | Counterparty-authored documents are untrusted input | Trust boundary plus controls that do not rely on compliance |
| **Silent quality drift** | A model update could degrade behaviour unnoticed | Reproducible evaluation; versioned prompts recorded per step |
| **Inconsistency** | Two runs producing different ratings destroys trust | Temperature 0; deterministic scoring |
| **Provider dependency** | Vendor change should not be a rebuild | Provider abstraction; no SDK outside `ai/providers/` |
| **Over-scoping** | Applying AI to arithmetic adds error for no gain | Explicit split, documented in this table |

---

## 6. Alternatives considered

### 6.1 Rules-based extraction (no LLM)

Regular expressions and templates over known document structures.

**Rejected.** Brittle across issuers and formats, cannot generalise to a new
document type, and unable to judge materiality. It would work for a fixed
template and fail on the second counterparty. Retained in spirit: the *numeric*
comparisons are rules.

### 6.2 A single large prompt

One model call: documents in, assessment out.

**Rejected.** No intermediate artefact to verify, no place to insert controls,
no ability to challenge a finding independently, no per-step attribution when
quality moves, and no way to fail one step without failing everything. It would
be less code and dramatically less trustworthy.

### 6.3 Fine-tuning a model on historical assessments

**Rejected for this stage.** Requires a volume of labelled historical
assessments that does not exist here, bakes in past inconsistency, makes
behaviour changes slow, and — critically — would not remove the need for any of
the controls, since a fine-tuned model still fabricates. Worth revisiting once
override data provides a calibration signal.

### 6.4 Fully autonomous assessment

**Rejected on principle.** The institution is accountable. Beyond that, it would
remove the only reliable check on the model's failure modes.

### 6.5 A conversational assistant over the document set

Chat as the primary interface.

**Rejected as the primary product**, retained as a secondary feature. Chat
produces no reviewable artefact, no consistency across analysts, and no audit
trail of what was concluded. Ask ARGUS exists to interrogate the structured
record — not to replace it.

### 6.6 Model-generated confidence scores

**Rejected.** Stated confidence is uncalibrated. Presenting it as a probability
would be the single most misleading thing the product could do.

---

## 7. Conclusion

AI is appropriate here because the bottleneck is reading comprehension over
fragmented prose, and because adversarial reasoning — the thing people do least
reliably — is something a model does consistently.

It is inappropriate for verification, aggregation, arithmetic, controls and
decisions. The architecture reflects that split precisely: roughly half the
pipeline runs no model at all, and the half that does is bounded on both sides
by code that does not trust it.

The measure of success is not that an LLM produced an assessment. It is that a
named analyst produced a better one, faster, and can prove where every line came
from.

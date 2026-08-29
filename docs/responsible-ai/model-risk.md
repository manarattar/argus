# Model Risk Assessment

> Fictional assessment written for the ARGUS demonstration, in the shape a model
> risk function would expect.

Thirteen risks, each with impact, mitigation, **residual risk** and how it is
tested. The residual column is the important one: a mitigation with no stated
residual risk is a claim, not an assessment.

**Overall residual risk: Medium.** Appropriate for a decision-support prototype
with mandatory human review. Not appropriate for production without the controls
listed in [`../architecture/security.md`](../architecture/security.md).

---

## MR-1 · Hallucinated evidence

**Risk** The model produces a quote, figure or statement that does not appear in
any source document.

**Impact** *High.* A fabricated quote in a risk assessment could contribute to a
wrong credit decision and would fail any audit.

**Mitigation**
- Every quote is re-matched against the stored source chunk by deterministic
  string algorithms (`ai/tools/grounding.py`). Unverifiable evidence is discarded
  before any downstream agent sees it.
- Evidence whose quote matches a *different* chunk than cited has its reference
  corrected rather than being discarded.
- Rejected evidence is retained and displayed, so the control is auditable.
- Findings may cite evidence only by identifier; unresolvable identifiers are
  stripped.

**Residual risk** *Low-Medium.* A quote can be verbatim yet materially
misleading in isolation — a real sentence lifted from a context that reverses its
meaning. Grounding verifies provenance, not interpretation. The Verifier and
Challenger partially address this; a human reading the source is the real
control.

**Testing** `tests/unit/test_grounding.py` (12 cases, majority negative);
evaluation `gnd-001`–`gnd-007`; `test_investigation_flow.py` plants a fabricated
quote and asserts rejection.

---

## MR-2 · Automation bias

**Risk** The analyst accepts a fluent, confident assessment without genuine
scrutiny. This is the most likely failure mode in practice, and the hardest to
detect.

**Impact** *High.* Defeats the entire human-in-the-loop control and creates the
appearance of oversight without the substance.

**Mitigation**
- No confidence percentages anywhere. Interpretable bands with rationale.
- Contradicting evidence displayed beside supporting evidence, not in a separate
  view.
- The Challenger produces arguments *against* the findings by default.
- Overrides require a written rationale.
- Override rate is a headline operational metric, with near-zero documented as a
  warning sign.
- Rejected evidence and failed steps are shown, so the system visibly makes
  mistakes rather than appearing infallible.

**Residual risk** *Medium.* No technical control forces genuine engagement. The
override rate makes the problem visible after the fact but does not prevent it.
Real mitigation is operational: review sampling, and training that treats the
tool as a colleague to argue with.

**Testing** Not testable in software. Measured in production via override rate
and reviewer sampling.

---

## MR-3 · Prompt injection via document content

**Risk** A case document contains text instructing the model to change its
behaviour — assign a low rating, ignore a category, reveal its instructions. In a
real deployment, documents may be authored by the counterparty.

**Impact** *High.* A counterparty able to influence its own risk assessment is a
serious control failure.

**Mitigation**
- All retrieved content is enclosed in labelled blocks; every system prompt
  states that content inside those blocks is data, never instruction
  (`ai/prompts/library.py`).
- Attempts to close the boundary tag early are neutralised by escaping.
- Controls that do not depend on model compliance: an injected instruction cannot
  create evidence that passes grounding, cannot make a citation resolve, and
  cannot alter the computed rating.
- Escalation rules are evaluated in code from domain data.

**Residual risk** *Medium.* Prompt-level defences are not guarantees, and a
sufficiently novel injection may succeed against the *generation* step. The
architecture bounds the damage — a compromised extraction still cannot produce
grounded evidence or move the score directly — but a suppressed finding (the
model declining to extract something) is not prevented by any downstream control.
Coverage measurement partially detects this by flagging a category with no
evidence.

**Testing** Structural cases `inj-001`–`inj-003` verify boundary enforcement and
run everywhere. Behavioural cases `inj-010`–`inj-012` check the model ignores
three injection styles and require a backend.

---

## MR-4 · Unsupported or overstated conclusions

**Risk** A finding is directionally reasonable but stated more strongly than the
evidence carries — "significant deterioration" where the evidence shows a modest
decline.

**Impact** *Medium-High.* Erodes analyst trust and distorts the rating.

**Mitigation**
- The Verifier assesses each claim against its citations with a four-valued
  verdict, and `partially_supported` exists precisely for this case.
- Evidence strength reflects corroboration and independence.
- Unverified claims drag the composite score down.
- The Challenger explicitly checks for conclusions stronger than the evidence.

**Residual risk** *Medium.* The Verifier shares a model family with the producer
and therefore shares some blind spots. A second independent model would reduce
this; it is on the roadmap rather than implemented.

**Testing** Evaluation `con-002` plants an overstated conclusion and expects a
challenge; `unc-*` cases pin the strength bands.

---

## MR-5 · False precision in confidence

**Risk** Presenting model-stated confidence as a calibrated probability.

**Impact** *Medium-High.* A "94% confident" label invites exactly the unearned
trust the product exists to resist.

**Mitigation** No numeric confidence is displayed anywhere. Evidence strength is
computed from observable signals and shown as one of four bands, always with its
rationale. The underlying score is available but presented as a band.

**Residual risk** *Low.* The bands themselves are a designed heuristic, not a
calibrated measure, and are described that way.

**Testing** `test_uncertainty_and_value.py::TestEvidenceStrength`; evaluation
`unc-001`–`unc-005`.

---

## MR-6 · Retrieval failure

**Risk** The relevant section is not retrieved, so a material risk is never
considered. Silent, and therefore dangerous.

**Impact** *High.* An absent finding is harder to notice than a wrong one.

**Mitigation**
- Hybrid retrieval, so keyword and semantic failure modes do not coincide.
- Category-driven retrieval passes rather than one broad query.
- Retrieval quality is computed and fed into the uncertainty model.
- Coverage measures against what a complete file should contain, so a category
  with no evidence is flagged as Missing rather than passing silently.

**Residual risk** *Medium.* Coverage detects a wholly missed category; it does
not detect a missed *document section* within a covered category. Retrieval
evaluation measures ranking on known queries, which is a proxy for recall rather
than recall itself.

**Testing** Evaluation `ret-001`–`ret-012`, `pol-001`–`pol-008`, scored by
reciprocal rank.

---

## MR-7 · Model or provider drift

**Risk** A provider updates a model and behaviour changes without any code
change.

**Impact** *Medium-High.* Silent quality degradation is worse than an outage.

**Mitigation** Reproducible evaluation suite; prompts versioned with the
reference recorded on every step; each evaluation run records model, backend and
embedding provider; deterministic layers are unaffected by model change.

**Residual risk** *Medium.* Detection depends on the suite being run regularly
and on it covering the behaviour that drifted. Fifty-three cases is a starting
point, not comprehensive coverage.

**Testing** `make eval`, intended to run in CI and before any model change.

---

## MR-8 · Structured output failure

**Risk** The model returns malformed or schema-invalid output.

**Impact** *Low-Medium.* Handled, but an unhandled version would corrupt state.

**Mitigation** Pydantic validation on every agent boundary with `extra="forbid"`;
retry with the validation error fed back; visible failure after the budget;
partial results preserved.

**Residual risk** *Low.* Well covered by construction.

**Testing** `test_investigation_flow.py::TestFailureHandling` asserts a failed
step is recorded and nothing is substituted; evaluation `str-001`, `str-002`.

---

## MR-9 · Inconsistency between runs

**Risk** The same file produces different ratings on different runs.

**Impact** *Medium-High.* Destroys analyst trust quickly.

**Mitigation** Temperature 0; deterministic sequencing; the rating computed by
arithmetic, so identical findings always produce an identical rating.

**Residual risk** *Low-Medium.* Model sampling is not perfectly deterministic
even at temperature 0, so *findings* may vary slightly between runs. The
mapping from findings to rating does not.

**Testing** `test_scoring.py` pins the deterministic layer.

---

## MR-10 · Bias

**Risk** Systematic differential treatment by sector, jurisdiction, company size
or the language of the source documents.

**Impact** *High* if present — potentially discriminatory outcomes and regulatory
exposure.

**Mitigation** Findings must be anchored to evidence; the rating is computed from
severity, likelihood and evidence quality only; category-level distribution is
visible in operations metrics.

**Residual risk** *High — and largely unassessed.* This is the weakest area of
the assessment and is stated as such. One synthetic counterparty cannot reveal
bias. Proper assessment needs a corpus spanning sectors, jurisdictions and
document languages, with outcomes compared across them. Not possible in a
portfolio project with invented data.

**Testing** None currently. Would require the corpus described above.

---

## MR-11 · Exposure of model reasoning

**Risk** Displaying intermediate chain-of-thought to end users.

**Impact** *Medium.* Leakage risk, and a poor basis for a decision — reasoning
traces read as more authoritative than they are.

**Mitigation** Traces record what each step *did* — capability, retrieval counts,
duration, tokens, cost — and never model reasoning. Chain-of-thought is not
requested, stored or displayed.

**Residual risk** *Low.*

**Testing** Trace payloads carry only structured step metadata.

---

## MR-12 · Data privacy

**Risk** Case documents containing personal or confidential data sent to a
third-party model provider.

**Impact** *High* in production. Not applicable in this demonstration, where all
data is synthetic.

**Mitigation in this prototype** All data is synthetic; the corpus is in the
repository; no PII is present; the local embedding path sends nothing externally.

**Required before production** Data classification before submission; PII
detection and redaction; provider agreements with no-training guarantees; a
deployment option with self-hosted inference; retention limits on prompts and
recordings; egress control.

**Residual risk** *High for production use as-is.* Documented rather than
mitigated, because mitigating it properly is an infrastructure exercise outside
this project's scope.

**Testing** Not applicable to synthetic data.

---

## MR-13 · Provider dependency

**Risk** Availability, pricing or policy change at a single model provider.

**Impact** *Medium.*

**Mitigation** Provider abstraction with no vendor SDK outside `ai/providers/`;
two live implementations plus replay; provider selected by configuration;
deterministic layers unaffected by outage.

**Residual risk** *Low-Medium.* Prompts are tuned against a specific model
family, so a provider switch would need an evaluation run to confirm behaviour
holds.

**Testing** `test_api.py` asserts the runtime reports the active backend;
`make doctor` reports resolved configuration.

---

## Summary

| ID | Risk | Impact | Residual |
|---|---|---|---|
| MR-1 | Hallucinated evidence | High | Low-Medium |
| MR-2 | Automation bias | High | **Medium** |
| MR-3 | Prompt injection | High | **Medium** |
| MR-4 | Overstated conclusions | Med-High | Medium |
| MR-5 | False precision | Med-High | Low |
| MR-6 | Retrieval failure | High | **Medium** |
| MR-7 | Model drift | Med-High | Medium |
| MR-8 | Structured output failure | Low-Med | Low |
| MR-9 | Run inconsistency | Med-High | Low-Medium |
| MR-10 | Bias | High | **High — unassessed** |
| MR-11 | Reasoning exposure | Medium | Low |
| MR-12 | Data privacy | High | **High for production** |
| MR-13 | Provider dependency | Medium | Low-Medium |

The three genuinely open items are **bias (MR-10)**, **production data privacy
(MR-12)** and **automation bias (MR-2)**. The first two are outside what a
synthetic-data prototype can address. The third is primarily an operational
control, not a technical one, and is the reason override rate is measured rather
than assumed away.

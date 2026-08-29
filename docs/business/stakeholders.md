# Stakeholders

> Fictional personas written for the ARGUS demonstration.

Four groups, each of which can kill the product for a different reason. The
design decisions that follow from each are listed, because a persona that does
not change the build is decoration.

---

## 1. Risk Analyst — *primary user*

**Priya, 4 years in counterparty risk, covers industrials.**

Prepares eight to twelve assessments a month. Judged on the quality of her packs
and on whether her recommendations survive senior review.

### Needs

- Find material evidence without reading everything twice.
- Cite a source locator without going back to the document.
- Be shown the counter-case before her reviewer finds it.
- Distinguish a finding backed by three sources from one backed by an ambiguous
  sentence.
- Disagree with the system easily, and have the disagreement stick.

### Fears

- Being handed a confident summary she cannot check, and being accountable for it.
- Missing something the tool did not surface, with no way to know it was missing.
- Spending longer verifying AI output than she would have spent doing the work.

### What her needs forced in the build

- Verbatim quotes with document and section on every evidence item.
- Contradicting evidence shown beside supporting evidence, not in a separate tab.
- Evidence-strength bands with the rationale always attached.
- Override in two clicks, with rationale mandatory and the rating recomputed
  immediately.
- Rejected evidence shown, so she can see what the system threw away.

---

## 2. Senior Risk Reviewer — *approver*

**Marcus, 15 years, signs off roughly sixty assessments a month.**

Accountable for what he approves. Reads packs quickly and probes the weakest
point.

### Needs

- The assessment and its one or two drivers, immediately.
- To see where the analyst overrode the system, and why.
- Unresolved contradictions surfaced rather than smoothed over.
- To trace any conclusion to a page.
- To know what the file does not contain.

### Fears

- An analyst rubber-stamping AI output, and him rubber-stamping the analyst.
- Being unable to reconstruct the basis of a decision months later.

### What his needs forced in the build

- Executive summary that leads with the assessment and its drivers.
- Analyst adjustments as a named report section, showing AI value beside human value.
- Unresolved challenges as a first-class field.
- The Evidence Graph — lineage from rating to page in one click.
- Investigation completeness measured against what a *complete file* contains.
- Mandatory escalation rules that block approval outright.

---

## 3. AI / Product Owner — *accountable for the product*

**Sofia, accountable for whether this earns its cost and its risk.**

### Needs

- Evidence it improves outcomes, not just speed.
- Adoption and override rates.
- Cost per investigation.
- Failure rates and their causes.
- A defensible answer to "how do you know it works?"

### Fears

- Rollout that looks successful because nobody is really using it.
- An incident traced back to an unchallenged AI conclusion.
- Quality that degrades on a model update, unnoticed.

### What her needs forced in the build

- Override rate as a headline metric, with both failure directions documented.
- Per-capability cost, latency and failure attribution.
- Reproducible evaluation suite, with **coverage** reported beside pass rate.
- Versioned prompts recorded on every step, so a metric change is attributable.
- Grounding rejection rate — evidence the control is doing work.

---

## 4. AI / Platform Engineer — *maintainer*

**Tom, maintains shared AI capabilities across several risk domains.**

### Needs

- Capabilities reusable across review types without forking.
- Model provider swappable by configuration.
- Typed boundaries so a change surfaces at build time.
- Observability at the step level.
- Tests that fail when behaviour regresses.

### Fears

- Domain logic leaking into shared capabilities until nothing is reusable.
- Vendor lock-in through SDK calls scattered across the codebase.
- Prompt changes with no way to attribute a metric movement.

### What his needs forced in the build

- `DomainConfig` as the single seam; no counterparty logic in any agent.
- One `LLMProvider` interface; no vendor SDK outside `ai/providers/`.
- Pydantic contracts on every agent boundary, `extra="forbid"`.
- Step traces with prompt reference, model, attempts, tokens and cost.
- Deterministic controls tested independently of any model.

---

## Tension between stakeholders

Worth naming, because the resolutions are visible in the product.

| Tension | Resolution |
|---|---|
| Analyst wants speed; Reviewer wants depth | Speed comes from preparation, not from shortening review. Review time is explicitly *not* reduced in the value model. |
| Product Owner wants adoption; Reviewer fears rubber-stamping | Override rate is measured and both extremes are documented as failure modes. |
| Engineer wants generic capabilities; Analyst wants domain specificity | Specificity lives in configuration; capabilities stay generic. |
| Everyone wants confidence scores; none of them are calibrated | Interpretable bands computed from observable signals, never a percentage. |

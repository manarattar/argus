# Demo Script

A 4–5 minute walkthrough that tells one story: **AI investigates and recommends;
a human decides — and every step of that is verifiable.**

Resist clicking everything. The features that land are the ones you connect to a
reason.

---

## Before you start

```bash
make seed-full        # corpus + a completed investigation
make dev              # API on :8000, web on :3000
```

Open <http://localhost:3000> at 1600×1000 or wider. Check `make doctor` so you
can state truthfully whether you're on live inference or recorded responses.

Have `docs/responsible-ai/model-risk.md` open in a second tab — it's the document
people ask for.

---

## 0 · Frame it (15 seconds)

> This is an independent portfolio project. All the data is synthetic — the
> company doesn't exist, the policies are fictional. Nothing here is affiliated
> with any institution.
>
> It's a decision-support tool for financial risk analysts.

---

## 1 · Overview (30 seconds)

Land on the dashboard.

> Portfolio view: active cases, what's waiting on a human decision, average
> investigation time, override rate, evidence coverage, model cost.

Point at the sidebar footer.

> That indicator is permanent. You can always tell whether you're looking at
> live model output or recorded responses. I'll come back to why that matters.

**Say:** *This is a workflow product, not a chatbot. That framing drives
everything else.*

---

## 2 · The case (45 seconds)

Open **Northstar Manufacturing B.V.**

> Elevated, computed from the findings. Evidence strength Moderate.

Scroll to **How this rating was calculated**.

> This is the decision I'd most want to talk about. The rating is not generated
> by the model. The model supplies severity, likelihood and which evidence bears
> on what — things it's genuinely good at. A scoring engine combines them with
> arithmetic you could audit on paper.
>
> Every point is attributable. Peak risk pushed it up; documented mitigating
> factors pulled it down; incomplete coverage pushed it up, because an incomplete
> file is less reassuring than a complete one, not more.

**Say:** *Ask a model for "High or Moderate" and you get a label that moves
between runs and can't be reconciled with the findings. Compute it and you get
reproducibility, explainability, testability — and thresholds a risk function
owns rather than prompt text.*

---

## 3 · A finding (60 seconds)

**Findings** tab. Expand the concentration finding.

> Supporting evidence on the left. Contradicting evidence on the right — same
> prominence, deliberately. Confirmation bias is the main analytical failure mode
> here, so the counter-case isn't behind a tab.

Point at a quote.

> Verbatim, with document and page. Not decoration: every quote was re-matched
> against the stored source text before this finding was allowed to cite it.
> Anything that couldn't be located was discarded before the risk agent ever saw
> it.

Point at the evidence-strength badge; hover it.

> No confidence percentage anywhere in this product. A model's stated confidence
> isn't calibrated, and dressing it up as a probability invites exactly the
> automation bias this is designed to resist. Instead: a band, computed from
> corroborating citations, independent sources, grounding quality and the
> verifier's verdict — with the reasoning attached.

Scroll to **What would change my mind**.

> For each finding, the specific evidence that would raise or lower it. That's
> what a good analyst writes down and most systems never ask for.

---

## 4 · The Challenger (45 seconds)

Scroll to the challenges block.

> There's an agent whose only job is to attack the findings. It gets the complete
> evidence set — including items the risk agent didn't cite — because overlooked
> evidence is usually the strongest basis for a challenge.

Point at an unresolved challenge.

> Marked unresolved: the file can't settle it either way. That's surfaced rather
> than smoothed over, and it reduces the score, because a contested finding
> should be held with less conviction.

**Say:** *This is the strongest case for using a model here. Arguing against your
own analysis is cognitively expensive and people do it inconsistently. A model
does it every time and has no stake in the conclusion.*

Optionally click **Challenge this finding** for the on-demand version.

---

## 5 · Human override (60 seconds — the centrepiece)

Click **Change severity**. Pick a lower level.

> Two things. First, the rationale is mandatory — enforced in the service layer,
> not just the form, because an override with no reason is worthless in a review.

Type: *Recent controls materially reduce residual risk.*

Save. Watch the rating move.

> Second — and this is the part I care about — the AI's original recommendation
> is never overwritten. Both values are on the record.

Scroll to **Analyst adjustments**.

> That's what makes the override rate measurable. It's the most honest metric in
> the product: near zero means analysts are rubber-stamping, very high means the
> model isn't earning its place. Both are failure modes, and you can't see either
> unless you store the original.

Scroll to the **review gate**.

> The workflow stops here structurally. The graph has no edge past this point —
> completing an assessment requires a recorded decision by a named person. And if
> a mandatory escalation has fired, Approve is blocked. You can escalate or
> reject; you can't approve past a control.

---

## 6 · Evidence Graph (30 seconds)

**Open in Evidence Graph**. Click a risk node.

> Rating, to finding, to evidence, to source document — and out to the policy
> clauses it triggers.
>
> None of this is inferred. Because agents cite by identifier rather than by
> sentence, the lineage is a database query. Dashed lines are disagreement:
> contradicting evidence and challenges.

**Say:** *"Where did this come from?" is the question every reviewer asks. This
answers it in one click.*

---

## 7 · Evaluation Lab (45 seconds)

Navigate to **Evaluation Lab**.

> 100% pass rate. And 85% coverage, in red, right next to it.

Point at the callout.

> Eight cases were skipped, not passed. They need a live model backend. They're
> reported as skipped so the pass rate isn't inflated by cases that never ran.
>
> That distinction is the whole point of this page. A suite that scores 100% by
> not running is worse than one reporting honest gaps.

Scroll to categories.

> 45 deterministic cases — retrieval, grounding including negative cases that
> must be *rejected*, scoring, uncertainty, escalation, the prompt trust
> boundary. Those run on any clone with no API key.

**Say if asked:** *This suite caught a real bug. My scoring engine was calibrated
so a severe, well-evidenced finding couldn't reach High — which contradicted the
engine's own documented design. I fixed the engine, not the test.*

---

## 8 · Architecture (30 seconds)

Navigate to **Architecture**.

> Rendered from the running system — capabilities, domains, prompt versions and
> controls are read from the modules that define them, so this page can't drift
> from the code.

Scroll to **Platform vs domain**.

> One domain is built. Three are scoped and labelled "design only". The agents,
> retrieval, grounding, scoring and review workflow contain no
> counterparty-specific logic — that all lives in one configuration value.
>
> I could have shipped four half-built domains and it would look stronger. It
> would also be dishonest, which is the thing this project argues against
> everywhere else.

---

## 9 · Close (20 seconds)

> The through-line: AI investigates and recommends, a human decides, and every
> step is verifiable.
>
> About half this pipeline runs no model at all — grounding, integrity checks,
> scoring, escalation. The model does reading comprehension and adversarial
> reasoning, which it's good at. Code does verification and arithmetic, which it
> isn't.

---

## Optional detours

**Scenario Lab** (30s) — vary concentration from 62% to 30%, show the recompute.
Note it's a simulation over a declared variable, not a model imagining a
different company.

**AI Operations** (30s) — per-capability cost, override behaviour, and the
grounding rejection rate: evidence the control does work.

**Ask ARGUS** (30s) — ask something the file can't answer and show it refuse.
The refusal is more interesting than any answer.

**Report** (20s) — scroll to Analyst Adjustments and Limitations. Sections with
nothing to report say "none recorded" rather than disappearing.

---

## Timing

| Section | Time |
|---|---|
| Frame | 0:15 |
| Overview | 0:30 |
| Case + scoring | 0:45 |
| Finding | 1:00 |
| Challenger | 0:45 |
| **Override + gate** | **1:00** |
| Evidence Graph | 0:30 |
| Evaluation Lab | 0:45 |
| Architecture | 0:30 |
| Close | 0:20 |
| **Total** | **~6:20** |

Cut Architecture and the Challenger for a 4-minute version. Never cut the
override — it's the point of the product.

---

## If something breaks

Don't hide it. If a step failed, open the **Trace** tab.

> That's a failed step, recorded and shown. The system doesn't substitute content
> when a step fails — it says so, and the rating still stands because it was
> computed from what did succeed.

Handled honestly, a failure demonstrates the error handling better than a clean
run would.

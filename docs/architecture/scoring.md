# Scoring and Uncertainty

Reference for the two computations that decide what the product actually says.

---

## 1. The composite rating

### Step 1 — inherent score

```
inherent = severity.ordinal × likelihood.ordinal        (1..25)
```

Severity and likelihood are judged separately by the risk agent. Collapsing them
into a single "risk" judgement loses the distinction between a severe-but-rare
event and a moderate-but-near-certain one — exactly the distinction a reviewer
needs.

### Step 2 — evidence discount

```
adjusted = inherent × EVIDENCE_MULTIPLIER[band]
```

| Band | Multiplier |
|---|---|
| Strong | 1.00 |
| Moderate | 0.82 |
| Weak | 0.55 |
| Insufficient | 0.25 |

This single line is the anti-hallucination property expressed as arithmetic: a
finding the model states with total confidence but cannot evidence contributes a
quarter of its nominal weight.

### Step 3 — factors

Seven named factors, each with a ceiling. The findings carry most of the weight;
policy, coverage and review outcomes modify it.

| Factor | Range | Meaning |
|---|---|---|
| Peak risk | 0 … +75 | The highest evidence-adjusted finding |
| Risk breadth | 0 … +15 | Distinct categories carrying a material finding |
| Policy triggers | 0 … +10 | Clauses triggered or potentially breached |
| Information gaps | 0 … +8 | Expected evidence categories partial or missing |
| Material claims on thin evidence | 0 … +8 | Major/Severe findings with weak evidence |
| Documented mitigation | −12 … 0 | Evidenced mitigating factors |
| Verification drag | −12 … 0 | Claims the verifier could not fully support |
| Contested findings | −6 … 0 | Unresolved challenges |

Sum, clamp to 0–100.

### Step 4 — band

| Score | Rating |
|---|---|
| ≥ 66 | High |
| ≥ 46 | Elevated |
| ≥ 26 | Moderate |
| < 26 | Low |

---

## 2. Two rules that look counter-intuitive

### Missing information raises the score

An incomplete file is *less* reassuring than a complete one. If gaps lowered the
score, a thin file would read as a clean counterparty — the most dangerous
possible behaviour. Unknowns are therefore scored conservatively.

### A material claim on thin evidence adds points

The natural reading is that weak evidence should discount a finding to nothing.
But CRF 7.3 captures the better instinct: where a Major or Severe finding rests
on weak evidence, *the evidential gap is itself the decision-relevant fact*.
Discounting it to zero would let a serious but unproven claim disappear quietly.
So it is discounted (step 2) **and** flagged (this factor), and an escalation
rule fires.

---

## 3. How the weights were calibrated

Not by taste. Four anchor scenarios were defined first, weights chosen so the
engine reproduces them, then the scenarios written into the evaluation suite.

| Anchor | Expected |
|---|---|
| One minor, unlikely, well-evidenced finding | Low |
| Moderate finding, moderate evidence, some gaps | Moderate |
| Several major findings, mixed evidence, triggers, mitigants | Elevated |
| Severe, likely, well-evidenced finding | High |

The suite caught a real defect during development. An earlier calibration spread
weight evenly across all factors, making it arithmetically impossible for a
severe, well-evidenced, uncontested finding to reach High without also breaching
a policy clause — contradicting the engine's own documented design. The engine
was rebalanced; the test was not weakened.

These thresholds are policy parameters. A risk function would own and tune them
against real outcomes.

---

## 4. Evidence strength

Never a percentage. Computed from signals a reviewer can dispute.

| Signal | Contribution | Rationale |
|---|---|---|
| Corroborating citations | 0 … +0.72, saturating | The second quote is worth far more than the fifth |
| Independent sources | 0 … +0.20 | Three quotes from one document are one source |
| Grounding quality | −0.10 … +0.10 | Did the quotes actually verify? |
| Verifier verdict | −0.40 … +0.15 | An adversarial second pass |
| Contradicting evidence | −0.22 … 0 | Contested findings deserve less conviction |
| Blocking information gap | −0.10 | A known unknown weakens what we can assert |

Clamped to 0–1, then banded: ≥ 0.72 Strong, ≥ 0.50 Moderate, ≥ 0.28 Weak,
otherwise Insufficient.

### Two hard rules

These are rules, not weights, and they override the arithmetic:

1. **No usable citations → Insufficient.** No amount of other signal rescues a
   finding with nothing behind it.
2. **Verifier says unsupported → Insufficient.** Four citations cannot outvote a
   verdict that the citations do not carry the claim.

---

## 5. Investigation completeness

Measured against the domain's declared expected evidence, never against what the
model produced — otherwise "complete" would mean nothing more than "the model
stopped".

Only `fact` evidence counts. A category supported solely by the model's own
interpretations has not been evidenced.

| Status | Condition |
|---|---|
| Complete | ≥ 2 factual items |
| Partial | At least one item, but fewer than two factual |
| Missing | No evidence at all |

---

## 6. Escalation

Domain data evaluated in code, never inferred by a model. A control that depends
on a model choosing to honour it is not a control.

| Rule | Fires when |
|---|---|
| High overall | The rating is High |
| Potential breach | Any policy match typed `potential_breach` |
| Material risk, thin evidence | A Major/Severe finding banded Weak or Insufficient |

While any rule stands, approval is refused at the service layer and disabled in
the UI.

---

## 7. Worked example

Two findings: concentration (Major × Likely, Strong) and governance
(Major × Possible, Moderate). One threshold met. One of six coverage categories
missing. Three mitigating factors. One unresolved challenge.

```
concentration   4 × 4 = 16 × 1.00 = 16.0
governance      4 × 3 = 12 × 0.82 =  9.8

peak risk             16.0 / 25 × 75 = +48.0
risk breadth          2 of 3 × 15    = +10.0
policy triggers       1 of 3 × 10    =  +3.3
information gaps      1/6 × 8        =  +1.3
thin material claims  0              =   0.0
mitigation            3/6 × −12      =  −6.0
verification drag     0              =   0.0
contested findings    1/3 × −6       =  −2.0
                                       ------
                                        54.6  →  Elevated
```

Every line of that is visible in the UI.

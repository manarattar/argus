# Problem Statement — Counterparty Risk Review

> Fictional scenario written for the ARGUS demonstration. It describes a
> realistic shape of work, not any particular institution's process.

## 1. Context

A mid-sized commercial bank maintains credit and operational exposure to several
thousand corporate counterparties. Each is reviewed at least annually by the
Counterparty Risk team: roughly forty analysts, organised by sector, producing
an assessment pack that a senior reviewer signs off.

The assessment is not a credit decision. It is the evidence base and reasoned
recommendation on which a decision is taken elsewhere — a limit renewal, a
pricing change, a covenant discussion, an escalation. Its value therefore lies
in being *complete, traceable and honest about uncertainty*, not in being fast.
Speed matters only to the extent that it buys more of those three.

## 2. Current-state workflow

```
1. Assemble the file        annual report, financial summary, governance review,
                            operational and technology assessments, RM notes,
                            prior assessment, public information

2. Read and extract         identify material statements across all sources

3. Analyse                  form findings; assign severity and likelihood

4. Test against policy      locate applicable framework clauses and thresholds

5. Challenge                actively look for evidence that cuts the other way

6. Record gaps              note what a complete file would contain but does not

7. Draft the pack           executive summary, findings, evidence, limitations,
                            recommended follow-up

8. Review                   senior reviewer challenges; analyst revises

9. Sign-off                 decision recorded, review cycle set
```

Steps 2 through 7 take the majority of the elapsed time. Steps 8 and 9 are where
the institutional value is created, and they are the steps most often
compressed when the earlier ones overrun.

## 3. Pain points

### 3.1 Evidence is fragmented and mostly boilerplate

The material statements in a two-hundred-page annual report might amount to
thirty sentences. Finding them is careful, unrewarding reading, and the cost is
paid again at every review.

### 3.2 Counter-evidence is systematically under-weighted

Once an analyst forms a view, the file tends to confirm it. The mitigating
paragraph three sections later is genuinely easy to miss — and it is precisely
what a senior reviewer will ask about. Nothing in the current process
*structurally* requires the counter-case to be constructed.

### 3.3 Traceability is reconstructed rather than captured

"Where does this figure come from?" is asked in most reviews. Answering it means
going back to the source, because the link between conclusion and page was never
recorded at the time it was made.

### 3.4 Policy thresholds are held in memory

The framework contains dozens of numbered thresholds. Applying them consistently
across forty analysts and several thousand counterparties depends on individual
recall, and drifts.

### 3.5 Absence is invisible

The document that is *not* in the file is the hardest thing to notice. A missing
audited account or an unsigned renewal is often the single most decision-relevant
fact, and there is no structural prompt to record it.

### 3.6 Uncertainty collapses into prose

"Concerns remain around governance" could mean three independent sources agree,
or one ambiguous sentence. The pack rarely distinguishes them, so the reviewer
cannot calibrate how hard to push.

### 3.7 Consistency is unmeasured

Whether two analysts would reach the same rating on the same file is not
currently knowable, because nothing records what was proposed versus what was
concluded.

## 4. Users

See [`stakeholders.md`](stakeholders.md). In short: the **Risk Analyst** prepares,
the **Senior Reviewer** challenges and signs, the **AI/Product Owner** is
accountable for whether the tool earns its place, and the **Platform Engineer**
maintains capabilities across review types.

## 5. The opportunity

Preparation is compressible; judgement is not. A system that produces a
*traceable, challenged, gap-aware evidence base* moves analyst time from
locating and transcribing toward interrogating and deciding.

Two secondary opportunities matter as much and are usually overlooked:

- **Consistency becomes measurable.** Storing the AI recommendation next to the
  human decision makes divergence visible for the first time.
- **Counter-evidence becomes structural.** An agent whose only job is to attack
  the findings does not get tired or invested in the conclusion.

## 6. Constraints

| Constraint | Consequence for the design |
|---|---|
| The institution is accountable for the decision | No autonomous completion path; human sign-off is structural |
| Model output cannot be trusted at face value | Deterministic verification of every citation |
| Assessments are audited | Append-only trail; both AI and human values retained |
| Ratings must be defensible and reproducible | Rating computed by arithmetic, not generated |
| Case documents are untrusted input | Prompt trust boundary plus architectural containment |
| Analysts are the scarce resource | The tool must save preparation time, not add review burden |
| Review types differ | Domain logic as configuration, not code |

## 7. Desired outcome

A named analyst, working a case, can:

1. see the material evidence, each traceable to a source locator;
2. see the findings that evidence supports, and the evidence against them;
3. see which policy clauses are engaged and on what numbers;
4. see how strongly each finding is evidenced, and why;
5. see what is missing from the file and what it would have told them;
6. disagree, record why, and watch the rating change accordingly;
7. produce a pack a senior reviewer can challenge line by line.

And the institution can answer, at any time: *who decided this, on what
evidence, and where did the system disagree with them?*

## 8. Explicit non-goals

- Making or recommending a credit decision.
- Replacing the senior review.
- Producing a rating without a human owner.
- Straight-through processing of any kind.

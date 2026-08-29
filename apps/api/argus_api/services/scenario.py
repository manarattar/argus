"""Scenario Lab: what happens to the rating if a structured input changes.

Honesty is the whole design constraint here. A scenario must not invent
evidence, and it must not ask a model to imagine a different company. So the
implementation is narrow on purpose:

* Scenarios operate on **declared structured variables** whose real values are
  extracted from case evidence and whose thresholds come from policy.
* Changing a variable adjusts the **severity and likelihood** of the findings
  that variable actually drives, according to explicit, inspectable rules.
* The **same deterministic scoring engine** then recomputes the rating.

No model call is involved. The result is a projection of the existing evidence
under a stated assumption, and every response is labelled as a simulation. It is
a legitimate simplification, and the limits are stated in the UI rather than
being glossed over.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ai.schemas.enums import Likelihood, RiskCategory, Severity
from ai.schemas.models import CoverageItem, RiskFinding
from ai.scoring.engine import compute_assessment_score
from argus_api.db.models import Evidence, Investigation
from argus_api.services.review import _to_finding

# Ordered scales used to step severity and likelihood up or down.
_SEVERITIES = [
    Severity.NEGLIGIBLE,
    Severity.MINOR,
    Severity.MODERATE,
    Severity.MAJOR,
    Severity.SEVERE,
]
_LIKELIHOODS = [
    Likelihood.RARE,
    Likelihood.UNLIKELY,
    Likelihood.POSSIBLE,
    Likelihood.LIKELY,
    Likelihood.ALMOST_CERTAIN,
]


@dataclass(frozen=True)
class ScenarioVariable:
    """A structured quantity a scenario may vary.

    ``thresholds`` map a policy limit to the severity a breach of it implies.
    They are policy parameters, not model output, which is what allows the
    projection to be explained by pointing at a clause.
    """

    key: str
    label: str
    unit: str
    description: str
    affects: tuple[RiskCategory, ...]
    thresholds: tuple[tuple[float, Severity], ...]
    policy_reference: str
    minimum: float = 0.0
    maximum: float = 100.0
    step: float = 1.0
    # Regex used to read the current value out of case evidence.
    extractor: str = ""
    fallback_value: float = 0.0
    higher_is_worse: bool = True


SCENARIO_VARIABLES: tuple[ScenarioVariable, ...] = (
    ScenarioVariable(
        key="customer_concentration",
        label="Top-two customer concentration",
        unit="% of revenue",
        description=(
            "Share of revenue attributable to the two largest customers. CRF 4.2 "
            "classifies more than 50% as material revenue concentration."
        ),
        affects=(RiskCategory.CONCENTRATION, RiskCategory.FINANCIAL),
        thresholds=(
            (70.0, Severity.SEVERE),
            (60.0, Severity.MAJOR),
            (50.0, Severity.MODERATE),
            (35.0, Severity.MINOR),
            (0.0, Severity.NEGLIGIBLE),
        ),
        policy_reference="CRF 4.2",
        minimum=10.0,
        maximum=90.0,
        step=1.0,
        extractor=r"two largest customers together accounted for (\d+)%",
        fallback_value=62.0,
    ),
    ScenarioVariable(
        key="net_leverage",
        label="Net debt / EBITDA",
        unit="x",
        description=(
            "Net leverage ratio. CRF 3.2 classifies above 2.0x as elevated "
            "financial leverage; the facility covenant is 3.25x."
        ),
        affects=(RiskCategory.FINANCIAL,),
        thresholds=(
            (3.25, Severity.SEVERE),
            (2.75, Severity.MAJOR),
            (2.00, Severity.MODERATE),
            (1.00, Severity.MINOR),
            (0.0, Severity.NEGLIGIBLE),
        ),
        policy_reference="CRF 3.2",
        minimum=0.0,
        maximum=5.0,
        step=0.1,
        extractor=r"net debt to EBITDA was ([\d.]+)x",
        fallback_value=2.4,
    ),
    ScenarioVariable(
        key="board_independence",
        label="Independent directors on the board",
        unit="% of board",
        description=(
            "Proportion of directors who are independent. GOS 1.2 classifies "
            "below one third as limited independent oversight."
        ),
        affects=(RiskCategory.GOVERNANCE,),
        thresholds=(
            (33.4, Severity.MINOR),
            (20.0, Severity.MODERATE),
            (10.0, Severity.MAJOR),
            (0.0, Severity.SEVERE),
        ),
        policy_reference="GOS 1.2",
        minimum=0.0,
        maximum=100.0,
        step=1.0,
        fallback_value=16.7,
        higher_is_worse=False,
    ),
    ScenarioVariable(
        key="supplier_buffer_days",
        label="Buffer stock for single-sourced components",
        unit="days",
        description=(
            "Inventory cover for single-sourced inputs, against a "
            "requalification lead time management estimates at 9-14 months."
        ),
        affects=(RiskCategory.SUPPLY_CHAIN, RiskCategory.OPERATIONAL),
        thresholds=(
            (180.0, Severity.MINOR),
            (120.0, Severity.MODERATE),
            (60.0, Severity.MAJOR),
            (0.0, Severity.SEVERE),
        ),
        policy_reference="CRF 4.4",
        minimum=0.0,
        maximum=365.0,
        step=5.0,
        fallback_value=118.0,
        higher_is_worse=False,
    ),
)

VARIABLES_BY_KEY = {v.key: v for v in SCENARIO_VARIABLES}


@dataclass
class VariableState:
    """A variable with its observed value and where that value came from."""

    key: str
    label: str
    unit: str
    description: str
    policy_reference: str
    current_value: float
    minimum: float
    maximum: float
    step: float
    source: str
    affects: list[str] = field(default_factory=list)


@dataclass
class FindingDelta:
    risk_id: str
    title: str
    category: str
    original_severity: str
    scenario_severity: str
    original_likelihood: str
    scenario_likelihood: str
    explanation: str


@dataclass
class ScenarioResult:
    """The full before/after comparison rendered by the Scenario Lab."""

    variable: str
    original_value: float
    scenario_value: float
    original_level: str
    original_score: float
    scenario_level: str
    scenario_score: float
    changed_findings: list[FindingDelta]
    unaffected_count: int
    factors: list[dict[str, Any]]
    explanation: str
    disclaimer: str = (
        "Simulation only. This projects the existing evidence under a stated "
        "assumption using the same deterministic scoring rules. It does not "
        "introduce new evidence, and it is not a finding about the counterparty."
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["changed_findings"] = [asdict(d) for d in self.changed_findings]
        return payload


def _severity_for(variable: ScenarioVariable, value: float) -> Severity:
    """Severity implied by a variable's value, per its policy thresholds."""
    if variable.higher_is_worse:
        for threshold, severity in variable.thresholds:
            if value >= threshold:
                return severity
        return Severity.NEGLIGIBLE
    # For "higher is better" variables the table is read from the top down as
    # the value falls below each threshold.
    for threshold, severity in variable.thresholds:
        if value >= threshold:
            return severity
    return variable.thresholds[-1][1]


def observed_values(session: Session, investigation: Investigation) -> list[VariableState]:
    """Read each variable's current value out of the case evidence.

    Falls back to a declared default when the regex does not match, and says so
    in ``source`` rather than presenting a default as an extracted figure.
    """
    evidence = session.query(Evidence).filter(Evidence.investigation_id == investigation.id).all()
    corpus = "\n".join(f"{e.statement}\n{e.quote}" for e in evidence)

    states: list[VariableState] = []
    for variable in SCENARIO_VARIABLES:
        value = variable.fallback_value
        source = "declared default (not located in extracted evidence)"
        if variable.extractor:
            match = re.search(variable.extractor, corpus, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    source = "extracted from case evidence"
                except (TypeError, ValueError):
                    pass
        states.append(
            VariableState(
                key=variable.key,
                label=variable.label,
                unit=variable.unit,
                description=variable.description,
                policy_reference=variable.policy_reference,
                current_value=value,
                minimum=variable.minimum,
                maximum=variable.maximum,
                step=variable.step,
                source=source,
                affects=[c.value for c in variable.affects],
            )
        )
    return states


def run_scenario(
    session: Session,
    investigation: Investigation,
    *,
    variable_key: str,
    scenario_value: float,
) -> ScenarioResult:
    """Recompute the rating with one structured variable changed.

    Raises:
        KeyError: The variable is not one of the declared scenario variables.
        ValueError: The value is outside the variable's permitted range.
    """
    variable = VARIABLES_BY_KEY[variable_key]
    if not variable.minimum <= scenario_value <= variable.maximum:
        raise ValueError(
            f"{variable.label} must be between {variable.minimum} and "
            f"{variable.maximum} {variable.unit}."
        )

    states = {s.key: s for s in observed_values(session, investigation)}
    original_value = states[variable_key].current_value

    original_severity = _severity_for(variable, original_value)
    scenario_severity = _severity_for(variable, scenario_value)
    severity_shift = _SEVERITIES.index(scenario_severity) - _SEVERITIES.index(original_severity)

    rows = [r for r in investigation.risks if not r.is_false_positive]
    baseline: list[RiskFinding] = []
    projected: list[RiskFinding] = []
    deltas: list[FindingDelta] = []
    affected = {c.value for c in variable.affects}

    for row in rows:
        finding = _to_finding(row)
        baseline.append(finding)

        if row.category not in affected or severity_shift == 0:
            projected.append(finding)
            continue

        new_severity = _shift(_SEVERITIES, finding.severity, severity_shift)
        # Likelihood moves at half the rate: a threshold breach makes a
        # consequence worse more directly than it makes the event likelier.
        likelihood_shift = severity_shift // 2 if abs(severity_shift) > 1 else 0
        new_likelihood = _shift(_LIKELIHOODS, finding.likelihood, likelihood_shift)

        projected.append(
            finding.model_copy(update={"severity": new_severity, "likelihood": new_likelihood})
        )
        deltas.append(
            FindingDelta(
                risk_id=row.risk_id,
                title=row.title,
                category=row.category,
                original_severity=finding.severity.value,
                scenario_severity=new_severity.value,
                original_likelihood=finding.likelihood.value,
                scenario_likelihood=new_likelihood.value,
                explanation=(
                    f"{variable.label} moves from {original_value:g} to "
                    f"{scenario_value:g} {variable.unit}, which under "
                    f"{variable.policy_reference} implies "
                    f"{scenario_severity.label} rather than "
                    f"{original_severity.label} severity for this category."
                ),
            )
        )

    coverage = [
        CoverageItem(
            category=item["category"],
            status=item["status"],
            expected=item.get("expected", ""),
            found_evidence_ids=item.get("found_evidence_ids", []),
            note=item.get("note", ""),
        )
        for item in (investigation.coverage or [])
    ]

    before = compute_assessment_score(baseline, coverage=coverage)
    after = compute_assessment_score(projected, coverage=coverage)

    direction = (
        "no change to"
        if after.overall_score == before.overall_score
        else ("raises" if after.overall_score > before.overall_score else "lowers")
    )
    explanation = (
        f"Moving {variable.label} from {original_value:g} to {scenario_value:g} "
        f"{variable.unit} {direction} the provisional rating "
        f"({before.overall_level.label} {before.overall_score:.0f} to "
        f"{after.overall_level.label} {after.overall_score:.0f}). "
        f"{len(deltas)} of {len(rows)} finding(s) are affected, all in "
        f"{', '.join(sorted(affected))}."
    )

    return ScenarioResult(
        variable=variable.key,
        original_value=original_value,
        scenario_value=scenario_value,
        original_level=before.overall_level.value,
        original_score=before.overall_score,
        scenario_level=after.overall_level.value,
        scenario_score=after.overall_score,
        changed_findings=deltas,
        unaffected_count=len(rows) - len(deltas),
        factors=[f.model_dump() for f in after.factors],
        explanation=explanation,
    )


def _shift(scale: list[Any], current: Any, steps: int) -> Any:
    """Move along an ordered scale, clamped at both ends."""
    index = scale.index(current)
    return scale[max(0, min(len(scale) - 1, index + steps))]

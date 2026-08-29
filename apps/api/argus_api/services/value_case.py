"""Illustrative business-case model.

Every input is an assumption the user can change, and every output is arithmetic
over those assumptions. Nothing here is measured from a real deployment, and the
API says so on every response.

The model is deliberately conservative in three ways, because a business case
that only works when read optimistically is not a business case:

* The analyst-hours saving is applied to *preparation* time only. Review,
  judgement and sign-off are unchanged - the product does not remove them, and
  claiming otherwise would contradict the human-in-the-loop design.
* Saved hours are valued as **capacity**, not cash. Nobody is removed from a
  team because a tool got faster; the honest claim is more reviews per analyst.
* An adoption factor scales the benefit, because a tool nobody uses saves
  nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

DISCLAIMER = (
    "Illustrative business-case model using configurable assumptions. Figures "
    "are not measured from a production deployment and are not the data of any "
    "institution. Saved hours are expressed as analyst capacity released, not "
    "as cost removed."
)


@dataclass
class ValueAssumptions:
    """Every input to the model. All are user-editable in the UI."""

    cases_per_month: float = 120.0
    manual_hours_per_case: float = 6.5
    assisted_hours_per_case: float = 3.4
    analyst_cost_per_hour: float = 85.0
    ai_cost_per_case: float = 0.42
    implementation_cost: float = 180_000.0
    annual_run_cost: float = 60_000.0
    adoption_rate: float = 0.7
    review_hours_per_case: float = 1.2

    def validate(self) -> None:
        if self.cases_per_month <= 0:
            raise ValueError("Cases per month must be greater than zero.")
        if self.assisted_hours_per_case > self.manual_hours_per_case:
            raise ValueError("AI-assisted hours per case cannot exceed manual hours per case.")
        if not 0.0 <= self.adoption_rate <= 1.0:
            raise ValueError("Adoption rate must be between 0 and 1.")
        if min(self.analyst_cost_per_hour, self.ai_cost_per_case) < 0:
            raise ValueError("Costs cannot be negative.")


@dataclass
class ValueResult:
    """Computed outputs, all derived from the assumptions above."""

    monthly_manual_hours: float
    monthly_assisted_hours: float
    monthly_hours_saved: float
    hours_saved_per_case: float
    monthly_capacity_value: float
    monthly_ai_cost: float
    monthly_run_cost: float
    monthly_net_value: float
    annual_net_value: float
    break_even_months: float | None
    additional_cases_capacity: float
    effective_cases: float
    assumptions: dict[str, float] = field(default_factory=dict)
    disclaimer: str = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute(assumptions: ValueAssumptions) -> ValueResult:
    """Run the model.

    Raises:
        ValueError: An assumption is outside a sensible range.
    """
    assumptions.validate()

    # Only the adopted share of cases sees any benefit.
    effective_cases = assumptions.cases_per_month * assumptions.adoption_rate
    unassisted_cases = assumptions.cases_per_month - effective_cases

    manual_hours = assumptions.cases_per_month * assumptions.manual_hours_per_case
    assisted_hours = (
        effective_cases * assumptions.assisted_hours_per_case
        + unassisted_cases * assumptions.manual_hours_per_case
    )
    hours_saved = max(0.0, manual_hours - assisted_hours)

    capacity_value = hours_saved * assumptions.analyst_cost_per_hour
    ai_cost = effective_cases * assumptions.ai_cost_per_case
    run_cost = assumptions.annual_run_cost / 12.0
    net_monthly = capacity_value - ai_cost - run_cost

    break_even = (
        round(assumptions.implementation_cost / net_monthly, 1) if net_monthly > 0 else None
    )

    # Released hours expressed as extra reviews the same team could complete.
    additional_capacity = (
        hours_saved / assumptions.manual_hours_per_case
        if assumptions.manual_hours_per_case > 0
        else 0.0
    )

    return ValueResult(
        monthly_manual_hours=round(manual_hours, 1),
        monthly_assisted_hours=round(assisted_hours, 1),
        monthly_hours_saved=round(hours_saved, 1),
        hours_saved_per_case=round(
            assumptions.manual_hours_per_case - assumptions.assisted_hours_per_case, 2
        ),
        monthly_capacity_value=round(capacity_value, 2),
        monthly_ai_cost=round(ai_cost, 2),
        monthly_run_cost=round(run_cost, 2),
        monthly_net_value=round(net_monthly, 2),
        annual_net_value=round(net_monthly * 12.0, 2),
        break_even_months=break_even,
        additional_cases_capacity=round(additional_capacity, 1),
        effective_cases=round(effective_cases, 1),
        assumptions=asdict(assumptions),
    )


def sensitivity(
    assumptions: ValueAssumptions,
    *,
    variable: str = "assisted_hours_per_case",
    spread: float = 0.4,
    points: int = 7,
) -> dict[str, Any]:
    """Vary one assumption and report how the annual outcome responds.

    Sensitivity analysis is what separates a business case from a spreadsheet
    with one flattering column: it shows which assumption the conclusion
    actually depends on.
    """
    base_value = getattr(assumptions, variable, None)
    if base_value is None:
        raise ValueError(f"Unknown assumption: {variable}")
    if not isinstance(base_value, int | float):
        raise ValueError(f"{variable} is not numeric.")

    low = base_value * (1 - spread)
    high = base_value * (1 + spread)
    step = (high - low) / max(points - 1, 1)

    series: list[dict[str, float | None]] = []
    for index in range(points):
        value = low + step * index
        candidate = ValueAssumptions(**{**asdict(assumptions), variable: value})
        try:
            result = compute(candidate)
        except ValueError:
            # Skip points the model considers invalid rather than reporting a
            # figure the model does not stand behind.
            continue
        series.append(
            {
                "value": round(value, 3),
                "annual_net_value": result.annual_net_value,
                "break_even_months": result.break_even_months,
            }
        )

    return {
        "variable": variable,
        "base_value": base_value,
        "series": series,
        "disclaimer": DISCLAIMER,
    }


DEFAULT_NOTES: dict[str, str] = {
    "cases_per_month": ("Counterparty reviews completed per month by the team in scope."),
    "manual_hours_per_case": (
        "Analyst hours per review today, covering evidence gathering, analysis " "and drafting."
    ),
    "assisted_hours_per_case": (
        "Analyst hours per review with ARGUS. Review and judgement time is "
        "unchanged; only preparation shortens."
    ),
    "analyst_cost_per_hour": "Fully loaded hourly cost of a risk analyst.",
    "ai_cost_per_case": (
        "Estimated model and infrastructure cost per investigation. The default "
        "is the order of magnitude observed on the demonstration case."
    ),
    "implementation_cost": ("One-off build, integration and change cost."),
    "annual_run_cost": "Ongoing platform, hosting and maintenance cost per year.",
    "adoption_rate": (
        "Share of eligible reviews actually run through the tool. A tool nobody "
        "uses saves nothing, so the benefit is scaled by this."
    ),
    "review_hours_per_case": (
        "Human review and sign-off time. Recorded for transparency and "
        "deliberately not reduced by the model."
    ),
}

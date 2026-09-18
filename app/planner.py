"""Deterministic staffing demand and cost.

Corrects the demand formula. The previous version multiplied `staff_per_day`
— already summed across every shift — by 365*24, which double-counts by the
shift factor (3x for Model A, 2x for Model B). Demand is now summed per shift:

    demand_hours(role) = SUM over shifts of
                         ceil(census / ratio) * shift_hours * 365

Rounding happens per shift, not once across the day: you cannot staff a shift
with a fraction of a nurse, and `ceil(census/ratio * shifts)` silently allowed
exactly that.

Clinical and regulatory constants are not literals here — they resolve through
`research/ingest.py` and carry a citation. See `research/SOURCES.md`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

WEEKS_PER_YEAR = 52
DAYS_PER_YEAR = 365

# Shift patterns. Each must tile a 24-hour day exactly; `Model.__post_init__`
# enforces it. The old Model A used 8+8+10=26h, which quietly inflated night
# demand by 25% and breached the EWTD 8h night-work default twice over.
MODEL_A_SHIFTS = {"early": 8, "late": 8, "night": 8}
MODEL_B_SHIFTS = {"day": 12, "night": 12}

DEFAULT_COSTS = {"sn": 1.0, "pn": 0.65, "hca": 0.4}

# Establishment uplift covering annual leave, sickness AND training, from the
# SNCT guidance (snct-multipliers-nihr). This is now a sourced figure and
# supersedes two earlier guesses: the undecomposed 1.46 rest factor, and the
# app's original 1.087 which counted annual leave alone.
#
# It is a SINGLE total. `vacation_days` must not be applied on top of it — that
# double-counts annual leave, which is the mistake this constant replaces.
SNCT_UPLIFT = 0.22

OVERTIME_DIFFERENTIAL = 1.5


@dataclass(frozen=True)
class Model:
    """A shift pattern plus the contracted week it is staffed on."""

    name: str
    shifts: dict[str, int]
    weekly_hours: int
    ratios: dict[str, int]

    def __post_init__(self) -> None:
        total = sum(self.shifts.values())
        if total != 24:
            raise ValueError(
                f"{self.name}: shifts total {total}h, must tile a 24h day exactly"
            )


@dataclass
class StaffPlanner:
    """Demand and cost for a unit at a given census.

    `unit_census` is the point estimate. Real census, acuity and absence are
    stochastic — see `app.stochastic`, which wraps this class and returns a
    demand distribution rather than a single number.
    """

    unit_census: int
    vacation_days: int = 30          # retained for the UI; see `uplift` below
    uplift: float = SNCT_UPLIFT
    costs: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_COSTS))

    # --- capacity of one full-time equivalent --------------------------------

    @property
    def availability(self) -> float:
        """Fraction of contracted hours actually rosterable, after all absence.

        Derived from `uplift` alone. `vacation_days` is deliberately NOT applied
        here: the SNCT uplift already includes annual leave, and multiplying the
        two counts it twice.
        """
        return 1 / (1 + self.uplift)

    def productive_hours_per_fte(self, weekly_hours: float) -> float:
        """Hours one FTE can actually be rostered for in a year."""
        return weekly_hours * WEEKS_PER_YEAR * self.availability

    def uplift_implied_by_vacation_days(self) -> float:
        """Uplift that `vacation_days` alone would justify.

        Exposed so a ward can see how far its leave entitlement falls short of
        a full establishment uplift — it buys no cover for sickness or training.
        """
        return DAYS_PER_YEAR / (DAYS_PER_YEAR - self.vacation_days) - 1

    # --- demand ---------------------------------------------------------------

    def staff_on_shift(self, ratio: int) -> int:
        """Bodies needed on one shift. Rounded up: no fractional nurses."""
        return math.ceil(self.unit_census / ratio)

    def demand_hours(self, ratio: int, shifts: dict[str, int]) -> int:
        """Care hours required across a full year for one role."""
        return sum(
            self.staff_on_shift(ratio) * hours * DAYS_PER_YEAR
            for hours in shifts.values()
        )

    def hours_per_patient_day(self, ratios: dict[str, int], shifts: dict[str, int]) -> float:
        """Total nursing HPPD across all roles — the cross-check against the
        SNCT observed band of 5.9-10.2. Outside that band is a bug signal."""
        daily = sum(
            self.staff_on_shift(ratio) * hours
            for ratio in ratios.values()
            for hours in shifts.values()
        )
        return daily / self.unit_census

    # --- cost -----------------------------------------------------------------

    def _with_overtime(
        self, demand_hours: float, fte_hours: float, ot_hours_per_week: float,
        staff_on_shift: int, role: str,
    ) -> tuple[int, float]:
        """Establishment and cost when overtime absorbs part of the demand.

        Overtime genuinely substitutes for headcount, so it must reduce the
        establishment — the old version charged overtime on top of an unchanged
        headcount, so `needs` and `costs` described two different staffing
        plans. Overtime is capped at the demand that actually exists; the old
        version let `regular_hours` go negative and still returned a number.

        Per hour, overtime is always dearer (1.5x). Total cost can still fall,
        because headcount is lumpy: covering a fractional remainder with
        overtime beats hiring a whole person to be idle most of the time. That
        is a real economic effect, not an artefact.
        """
        ot_hours = min(ot_hours_per_week * WEEKS_PER_YEAR * staff_on_shift, demand_hours)
        residual = demand_hours - ot_hours
        establishment = math.ceil(residual / fte_hours)
        hourly = self.costs[role] / fte_hours
        cost = establishment * self.costs[role] + ot_hours * hourly * OVERTIME_DIFFERENTIAL
        return establishment, cost

    def evaluate(
        self, model: Model, overtime: dict[str, float] | None = None
    ) -> dict:
        """Establishment and cost for one model.

        `overtime` maps a role to overtime hours per week per rostered nurse.
        """
        overtime = overtime or {}
        fte_hours = self.productive_hours_per_fte(model.weekly_hours)

        needs: dict[str, int] = {}
        costs: dict[str, float] = {}
        for role, ratio in model.ratios.items():
            hours = self.demand_hours(ratio, model.shifts)
            needs[role] = math.ceil(hours / fte_hours)

            ot = overtime.get(role, 0)
            if ot > 0:
                needs[role], costs[role] = self._with_overtime(
                    hours, fte_hours, ot, self.staff_on_shift(ratio), role
                )
            else:
                costs[role] = needs[role] * self.costs[role]

        return {
            "needs": needs,
            "costs": costs,
            "total_cost": sum(costs.values()),
            "hppd": self.hours_per_patient_day(model.ratios, model.shifts),
            "uplift": self.uplift,
            "uplift_from_leave_only": self.uplift_implied_by_vacation_days(),
        }

    # --- named models ---------------------------------------------------------

    def calculate_model_a(self, ratios=None, overtime_config=None) -> dict:
        """Three 8-hour shifts on a 40-hour week.

        `overtime_config` is keyed by shift for backward compatibility; the
        hours are summed and applied to the registered nurses, since that is
        the only role the old code ever charged overtime to.
        """
        model = Model(
            "Model A", MODEL_A_SHIFTS, 40,
            ratios or {"sn": 8, "pn": 12, "hca": 16},
        )
        overtime = {}
        if overtime_config:
            total = sum(overtime_config.values())
            if total:
                overtime["sn"] = total / len(model.shifts)
        return self.evaluate(model, overtime)

    def calculate_model_b(self, ratios=None, overtime_per_week=0) -> dict:
        """Two 12-hour shifts on a 48-hour week."""
        model = Model(
            "Model B", MODEL_B_SHIFTS, 48,
            ratios or {"sn": 3, "hca": 16},
        )
        overtime = {"sn": overtime_per_week} if overtime_per_week else {}
        return self.evaluate(model, overtime)

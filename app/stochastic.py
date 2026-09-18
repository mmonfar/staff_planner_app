"""Stochastic demand: census and acuity vary, so establishment is a percentile.

Two sourced findings force this, and they arrive independently:

* `demand.establishment_policy` — "policies meeting demand 90% of the time
  produced the best outcomes" (snct-nihr-2020). Planning to *mean* demand
  under-delivers roughly half the time, by construction.
* `acuity.cmi_to_dnw.r_squared` = 0.627 (yang-2023-bmcnurs). CMI explains ~63%
  of nursing-time variance. The other 37% is irreducible on the day.

So a single-number establishment is not a conservative answer, it is a
coin-flip. This module returns a distribution and takes a percentile off it.

Only the standard library is used — no new dependency, and a fixed seed makes
every run reproducible, which matters for a figure anyone might have to defend.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass, field

from app.acuity import (
    DEFAULT_BASE_MIX,
    DEFAULT_CMI_TILT,
    LEVELS,
    SNCT_GENERAL_WARD,
    AcuityMix,
    demand_hours_per_day,
    mix_from_cmi,
)
from app.planner import DAYS_PER_YEAR, Model, StaffPlanner
from app.wellbeing import ShiftPattern, absence_feedback

CMI_REFERENCE = 1.0

# Concentration of the Dirichlet the daily acuity mix is drawn from. Higher
# means the ward's case profile is more stable day to day. An assumption —
# estimate it from your own SNCT census history.
DEFAULT_MIX_CONCENTRATION = 40.0

# SNCT observed range across adult inpatient wards (snct-nihr-2020). Used as an
# output gate, not an input: a computed HPPD outside it is a bug signal.
HPPD_SANITY_BAND = (5.9, 10.2)

Z_P90 = 1.2816  # standard normal quantile, for the analytic cross-check

# Tolerance for the analytic cross-check. Demand is discrete — headcount is
# integer and shift hours are fixed — so the distribution is lumpy and a normal
# approximation will never match exactly. 10% flags a broken sampler without
# firing on ordinary discreteness.
BASELINE_DRIFT_TOLERANCE = 0.10


def acuity_factor(cmi: float, tilt: float = DEFAULT_CMI_TILT) -> float:
    """Demand multiplier relative to baseline complexity, via the SNCT ladder.

    Replaces an earlier quadratic fitted inside one surgical specialty, which
    produced only a 1.29x demand rise across a tripling of case mix. Routing
    CMI through the acuity ladder recovers the real spread, because the ladder
    was built by measuring nursing time rather than billing weight.
    """
    baseline = mix_from_cmi(CMI_REFERENCE, tilt=tilt).hppd()
    return mix_from_cmi(cmi, tilt=tilt).hppd() / baseline


def _poisson(rng: random.Random, lam: float) -> int:
    """Knuth sampler. Fine at the census magnitudes a single ward sees."""
    if lam <= 0:
        return 0
    target, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= target:
            return k
        k += 1


@dataclass
class DemandDistribution:
    """Sampled daily care-hour requirements."""

    samples: list[float]

    def percentile(self, p: float) -> float:
        if not 0 < p < 1:
            raise ValueError("p must lie strictly between 0 and 1")
        ordered = sorted(self.samples)
        idx = min(int(math.ceil(p * len(ordered))) - 1, len(ordered) - 1)
        return ordered[idx]

    @property
    def mean(self) -> float:
        return statistics.fmean(self.samples)

    @property
    def stdev(self) -> float:
        return statistics.stdev(self.samples)

    def analytic_p90(self) -> float:
        """Normal-approximation p90 — the cheap baseline the simulation must
        agree with. Divergence means the sampler is wrong, not that the
        simulation is cleverer."""
        return self.mean + Z_P90 * self.stdev


@dataclass
class StochasticPlanner:
    """Wraps `StaffPlanner` with day-to-day variability.

    `census_dispersion` is the variance-to-mean ratio. 1.0 is pure Poisson;
    real ward census is overdispersed (admissions cluster, discharges batch),
    so the default sits above it. It is an assumption, not a sourced figure —
    set it from your own occupancy history.
    """

    beds: int
    mean_census: float
    mean_cmi: float = 1.0
    cmi_sd: float = 0.15
    census_dispersion: float = 1.6
    cmi_tilt: float = DEFAULT_CMI_TILT
    mix_concentration: float = DEFAULT_MIX_CONCENTRATION
    ladder: dict = None
    unplanned_absence_rate: float = 0.05
    absence_is_endogenous: bool = True
    vacation_days: int = 30
    costs: dict[str, float] | None = None
    seed: int = 20260918
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.census_dispersion < 1:
            raise ValueError("census_dispersion < 1 is under-dispersed; not a ward")
        self._rng = random.Random(self.seed)

    # --- sampling -------------------------------------------------------------

    def _sample_census(self) -> int:
        """Negative binomial via a gamma-Poisson mixture, capped at bed count."""
        if self.census_dispersion == 1:
            draw = _poisson(self._rng, self.mean_census)
        else:
            shape = self.mean_census / (self.census_dispersion - 1)
            rate = self._rng.gammavariate(shape, (self.census_dispersion - 1))
            draw = _poisson(self._rng, rate)
        return max(1, min(draw, self.beds))

    def _sample_cmi(self) -> float:
        return max(0.1, self._rng.gauss(self.mean_cmi, self.cmi_sd))

    def _sample_mix(self, cmi: float) -> AcuityMix:
        """Dirichlet draw around the mix implied by the day's case mix index.

        The ward does not see its average patient profile every day: some days
        run heavy, some light, and that variation is a second source of demand
        risk on top of census.
        """
        expected = mix_from_cmi(cmi, tilt=self.cmi_tilt).proportions
        draws = {
            lvl: self._rng.gammavariate(
                max(expected[lvl] * self.mix_concentration, 1e-3), 1.0
            )
            for lvl in LEVELS
        }
        total = sum(draws.values())
        return AcuityMix({lvl: d / total for lvl, d in draws.items()})

    def simulate(self, model: Model, days: int = 10_000) -> DemandDistribution:
        """Sample the daily care-hour requirement."""
        samples = []
        for _ in range(days):
            census = self._sample_census()
            mix = self._sample_mix(self._sample_cmi())
            samples.append(demand_hours_per_day(census, mix, self.ladder))
        return DemandDistribution(samples)

    def ratio_capacity_hours(self, model: Model, census: int = None) -> float:
        """Care hours a ratio-based roster actually delivers in a day.

        The gap between this and acuity-driven demand is the whole question:
        a fixed ratio buys a fixed number of hours regardless of how ill the
        patients are.
        """
        census = round(self.mean_census) if census is None else census
        return sum(
            math.ceil(census / ratio) * sum(model.shifts.values())
            for ratio in model.ratios.values()
        )

    # --- establishment --------------------------------------------------------

    def establishment(self, model: Model, policy: float = 0.90, days: int = 10_000) -> dict:
        """FTE establishment sized to meet demand `policy` of the time.

        Returns the simulation alongside its analytic cross-check and the HPPD
        sanity gate, so a caller can see *why* a number is trustworthy rather
        than taking it on faith.
        """
        dist = self.simulate(model, days)
        planner = StaffPlanner(
            unit_census=round(self.mean_census), vacation_days=self.vacation_days,
            costs=dict(self.costs) if self.costs else None,
        )
        fte_hours = planner.productive_hours_per_fte(model.weekly_hours)

        target = dist.percentile(policy)
        fte = math.ceil(target * DAYS_PER_YEAR / fte_hours)
        ratio_hours = self.ratio_capacity_hours(model)

        # Unplanned absence erodes the roster on the day, so the establishment
        # carries it on top of the demand percentile.
        #
        # Absence is not a fixed input. Understaffing raises sickness absence,
        # which deepens the understaffing (dallora-2025-jamanetwopen), so a plan
        # that looks marginally adequate on paper degrades in service. The
        # shortfall a ratio-based roster is already running is fed back into the
        # absence rate before the establishment is sized.
        effective_absence = self.unplanned_absence_rate
        if self.absence_is_endogenous:
            shortfall = max(0.0, (target - ratio_hours) / target)
            effective_absence = absence_feedback(
                self.unplanned_absence_rate, shortfall,
                ShiftPattern(
                    shift_hours=max(model.shifts.values()),
                    weekly_hours=model.weekly_hours,
                    night_share=1 / len(model.shifts),
                ),
            )
        fte_with_absence = math.ceil(fte / (1 - effective_absence))

        # The SNCT band describes AVERAGE ward staffing requirements, so the
        # band check runs against mean HPPD. Establishment HPPD sits above it by
        # design — that headroom is the p90 policy, not an overshoot — and is
        # reported separately rather than measured against a mean-based band.
        hppd_mean = dist.mean / self.mean_census
        hppd_target = target / self.mean_census
        low, high = HPPD_SANITY_BAND

        analytic = dist.analytic_p90()
        simulated_p90 = dist.percentile(0.90)
        drift = abs(analytic - simulated_p90) / simulated_p90

        return {
            "policy": policy,
            "demand_mean": dist.mean,
            "demand_p50": dist.percentile(0.50),
            "demand_target": target,
            "establishment_fte": fte,
            "establishment_fte_with_absence": fte_with_absence,
            "hppd_mean": hppd_mean,
            "hppd_target": hppd_target,
            "hppd_in_band": low <= hppd_mean <= high,
            "analytic_p90": analytic,
            "analytic_drift": drift,
            "baseline_gate_passed": drift < BASELINE_DRIFT_TOLERANCE,
            "mean_vs_target_shortfall": (target - dist.mean) / dist.mean,
            "ratio_capacity_hours": ratio_hours,
            "ratio_meets_p90_demand": ratio_hours >= target,
            "ratio_gap_hours": ratio_hours - target,
            "absence_rate_used": effective_absence,
            "absence_rate_base": self.unplanned_absence_rate,
        }

    def shortfall_risk(self, model: Model, rostered: int, days: int = 10_000) -> float:
        """Fraction of days a given rostered headcount fails to meet demand.

        This is the operational counterpart to `establishment`: it answers
        "what did we buy?" rather than "what should we buy?".
        """
        dist = self.simulate(model, days)
        per_day_capacity = rostered * sum(model.shifts.values()) / len(model.shifts)
        short = sum(1 for h in dist.samples if h > per_day_capacity)
        return short / len(dist.samples)

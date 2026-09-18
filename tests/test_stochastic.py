"""Tests for the stochastic demand layer.

The simulation is checked against a cheap analytic baseline, per the
exact-before-elaborate discipline: if Monte Carlo and a normal approximation
disagree materially on the same distribution, the sampler is wrong. A
simulation that cannot be cross-checked is not evidence.
"""

import pytest

from app.acuity import LEVELS, SNCT_GENERAL_WARD, AcuityMix, mix_from_cmi
from app.planner import MODEL_A_SHIFTS, Model
from app.stochastic import (
    CMI_REFERENCE,
    HPPD_SANITY_BAND,
    DemandDistribution,
    StochasticPlanner,
    acuity_factor,
)

MODEL_A = Model("Model A", MODEL_A_SHIFTS, 40, {"sn": 8, "pn": 12, "hca": 16})
DAYS = 4000


@pytest.fixture
def sp():
    return StochasticPlanner(beds=36, mean_census=32, mean_cmi=1.0)


# --- the CMI bridge ---------------------------------------------------------

def test_acuity_factor_is_one_at_baseline_complexity():
    assert acuity_factor(CMI_REFERENCE) == pytest.approx(1.0)


def test_the_acuity_ladder_spans_a_sixfold_range():
    """Different patients do NOT require the same work time.

    This is the finding that overturned an earlier conclusion in this project
    that acuity was a weak lever — that came from a single-specialty fit with a
    restricted acuity range.
    """
    assert SNCT_GENERAL_WARD["3"] / SNCT_GENERAL_WARD["0"] == pytest.approx(6.02, abs=0.05)


def test_acuity_demand_accelerates_with_case_mix():
    """Convex, because the mix tilts toward levels that are themselves further
    apart. A linear scaling understates exactly the top end where staffing
    failures hurt."""
    step_low = acuity_factor(1.5) - acuity_factor(1.0)
    step_high = acuity_factor(2.5) - acuity_factor(2.0)
    assert step_high > step_low


def test_case_mix_is_a_strong_lever_not_a_marginal_one():
    """The superseded quadratic gave only +20% across CMI 1.0 -> 2.5. Routing
    CMI through the acuity ladder recovers the real spread."""
    assert acuity_factor(2.5) > 1.8


def test_a_mix_must_be_complete_and_normalised():
    with pytest.raises(ValueError, match="missing levels"):
        AcuityMix({"0": 1.0})
    with pytest.raises(ValueError, match="must sum to 1"):
        AcuityMix({lvl: 0.5 for lvl in LEVELS})


def test_rising_case_mix_shifts_patients_up_the_ladder():
    light = mix_from_cmi(1.0)
    heavy = mix_from_cmi(2.0)
    assert heavy.share_at_or_above("2") > light.share_at_or_above("2")
    assert heavy.mean_severity() > light.mean_severity()


def test_baseline_mix_lands_inside_the_snct_band():
    low, high = HPPD_SANITY_BAND
    assert low <= mix_from_cmi(CMI_REFERENCE).hppd() <= high


def test_acuity_factor_rises_with_case_mix():
    assert acuity_factor(2.0) > acuity_factor(1.0) > acuity_factor(0.5)


# --- the distribution -------------------------------------------------------

def test_percentile_rejects_degenerate_probabilities():
    dist = DemandDistribution([1.0, 2.0, 3.0])
    for bad in (0, 1, -0.1, 1.5):
        with pytest.raises(ValueError):
            dist.percentile(bad)


def test_percentiles_are_ordered():
    dist = DemandDistribution([float(x) for x in range(100)])
    assert dist.percentile(0.5) < dist.percentile(0.9) < dist.percentile(0.99)


def test_simulation_is_reproducible():
    a = StochasticPlanner(beds=36, mean_census=32, seed=7).simulate(MODEL_A, DAYS)
    b = StochasticPlanner(beds=36, mean_census=32, seed=7).simulate(MODEL_A, DAYS)
    assert a.samples == b.samples


def test_census_is_capped_at_the_bed_count(sp):
    dist = sp.simulate(MODEL_A, DAYS)
    assert max(dist.samples) < float("inf")
    assert min(dist.samples) > 0


def test_under_dispersion_is_rejected():
    with pytest.raises(ValueError, match="under-dispersed"):
        StochasticPlanner(beds=36, mean_census=32, census_dispersion=0.5)


# --- establishment ----------------------------------------------------------

def test_p90_establishment_exceeds_mean_demand(sp):
    """The whole reason this module exists. Planning to the mean under-delivers
    by construction; snct-nihr-2020 found p90 gave the best outcomes."""
    result = sp.establishment(MODEL_A, policy=0.90, days=DAYS)
    assert result["demand_target"] > result["demand_mean"]
    assert result["mean_vs_target_shortfall"] > 0


def test_higher_policy_never_buys_a_smaller_establishment(sp):
    lower = sp.establishment(MODEL_A, policy=0.50, days=DAYS)["establishment_fte"]
    higher = sp.establishment(MODEL_A, policy=0.95, days=DAYS)["establishment_fte"]
    assert higher >= lower


def test_unplanned_absence_increases_the_establishment(sp):
    result = sp.establishment(MODEL_A, days=DAYS)
    assert result["establishment_fte_with_absence"] >= result["establishment_fte"]


def test_simulation_agrees_with_its_analytic_baseline(sp):
    """The baseline gate. Monte Carlo must reproduce a normal approximation of
    its own p90 within tolerance; if it cannot, the sampler is the problem."""
    result = sp.establishment(MODEL_A, days=DAYS)
    assert result["baseline_gate_passed"], (
        f"analytic p90 {result['analytic_p90']:.1f} drifted "
        f"{result['analytic_drift']:.1%} from simulated"
    )


def test_computed_hppd_stays_inside_the_snct_band(sp):
    result = sp.establishment(MODEL_A, days=DAYS)
    low, high = HPPD_SANITY_BAND
    assert result["hppd_in_band"], f"mean HPPD {result['hppd_mean']:.2f} outside {low}-{high}"
    # Establishment HPPD must sit above the mean: that gap IS the p90 policy.
    assert result["hppd_target"] > result["hppd_mean"]


def test_higher_case_mix_demands_more_staff():
    light = StochasticPlanner(beds=36, mean_census=32, mean_cmi=0.8, seed=3)
    heavy = StochasticPlanner(beds=36, mean_census=32, mean_cmi=2.5, seed=3)
    assert (heavy.establishment(MODEL_A, days=DAYS)["establishment_fte"]
            > light.establishment(MODEL_A, days=DAYS)["establishment_fte"])


def test_a_modest_case_mix_rise_is_not_quantised_away():
    """CMI must remain a live lever at small movements."""
    base = StochasticPlanner(beds=36, mean_census=32, mean_cmi=1.0, seed=11)
    risen = StochasticPlanner(beds=36, mean_census=32, mean_cmi=1.6, seed=11)
    assert (risen.establishment(MODEL_A, days=DAYS)["demand_target"]
            > base.establishment(MODEL_A, days=DAYS)["demand_target"])


# --- operational risk -------------------------------------------------------

def test_a_fixed_ratio_stops_meeting_demand_as_acuity_rises(sp):
    """The core product insight: a ratio buys a fixed number of hours, and
    acuity does not care. The gap is the safety margin."""
    light = StochasticPlanner(beds=36, mean_census=32, mean_cmi=0.9, seed=5)
    heavy = StochasticPlanner(beds=36, mean_census=32, mean_cmi=2.2, seed=5)
    assert (heavy.establishment(MODEL_A, days=DAYS)["ratio_gap_hours"]
            < light.establishment(MODEL_A, days=DAYS)["ratio_gap_hours"])


def test_shortfall_risk_falls_as_rostered_staff_rises(sp):
    thin = sp.shortfall_risk(MODEL_A, rostered=8, days=DAYS)
    thick = sp.shortfall_risk(MODEL_A, rostered=40, days=DAYS)
    assert thin > thick
    assert 0.0 <= thick <= thin <= 1.0

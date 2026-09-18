"""Tests for the establishment solver, its baselines and the Pareto front."""

import pytest

from app.optimise import (
    DEFAULT_MIN_RN_SHARE,
    Establishment,
    _non_dominated,
    annual_cost,
    baseline_gate,
    pareto_front,
    solve,
)
from app.planner import MODEL_A_SHIFTS, MODEL_B_SHIFTS, Model

MODEL_A = Model("Model A", MODEL_A_SHIFTS, 40, {"sn": 8, "pn": 12, "hca": 16})
MODEL_B = Model("Model B", MODEL_B_SHIFTS, 48, {"sn": 3, "hca": 16})
DEMAND = 250.0  # care hours per day, roughly p90 for a 32-bed ward at CMI 1.0


# --- feasibility ------------------------------------------------------------

def test_solver_reaches_a_proven_optimum():
    assert solve(MODEL_A, DEMAND).status == "Optimal"


def test_solution_delivers_at_least_the_demanded_hours():
    assert solve(MODEL_A, DEMAND).care_hours >= DEMAND


def test_solution_meets_the_skill_mix_floor():
    e = solve(MODEL_A, DEMAND, min_rn_share=0.60)
    assert e.rn_share >= 0.60 - 1e-9


def test_every_shift_is_covered_and_mixed():
    """A global skill-mix floor alone is gameable: the solver will stack
    registered nurses onto one shift and leave the night with a single nurse,
    satisfying the daily average while being indefensible on the ward."""
    e = solve(MODEL_A, DEMAND)
    for shift, length in MODEL_A_SHIFTS.items():
        staffed = e.on_shift(shift)
        assert staffed, f"{shift} left unstaffed"
        assert staffed.get("sn", 0) >= 1, f"{shift} has no registered nurse"
        shift_hours = sum(n * length for n in staffed.values())
        rn_hours = staffed.get("sn", 0) * length
        assert rn_hours >= DEFAULT_MIN_RN_SHARE * shift_hours - 1e-9


def test_night_cover_is_not_sacrificed_to_the_day():
    e = solve(MODEL_A, DEMAND)
    night = sum(e.on_shift("night").values())
    early = sum(e.on_shift("early").values())
    assert night >= early / 2, "night stripped to fund the early shift"


# --- monotonicity -----------------------------------------------------------

def test_more_demand_never_costs_less():
    assert solve(MODEL_A, 400).daily_cost >= solve(MODEL_A, 250).daily_cost


def test_a_richer_required_mix_never_costs_less():
    lean = solve(MODEL_A, DEMAND, min_rn_share=0.40)
    rich = solve(MODEL_A, DEMAND, min_rn_share=0.80)
    assert rich.daily_cost >= lean.daily_cost


def test_annual_cost_scales_from_the_daily_figure():
    e = solve(MODEL_A, DEMAND)
    assert annual_cost(e) == pytest.approx(e.daily_cost * 365)


# --- wellbeing is carried through -------------------------------------------

def test_twelve_hour_pattern_is_flagged_non_compliant():
    """Model B's 12h nights breach the EWTD night-work default. The solver
    must not present a plan as optimal without saying so."""
    e = solve(MODEL_B, DEMAND)
    assert not e.compliant
    assert any("night-work default" in b for b in e.breaches)
    assert solve(MODEL_A, DEMAND).compliant


def test_eight_hour_pattern_scores_better_on_wellbeing():
    assert solve(MODEL_A, DEMAND).wellbeing_score > solve(MODEL_B, DEMAND).wellbeing_score


# --- the baseline gate ------------------------------------------------------

def test_solver_beats_both_baselines():
    """Required before any solver result is reportable. If an optimiser cannot
    beat blind sampling, the objective or the encoding is broken and tuning the
    optimiser hides it."""
    gate = baseline_gate(MODEL_A, DEMAND, evaluations=3000)
    assert gate.beats_random
    assert gate.beats_hill_climb
    assert gate.passed


def test_the_hill_climber_actually_finds_something():
    """Guards a vacuous gate.

    With infeasible plans scored as infinity the climber has a flat landscape,
    never reaches feasibility, and reports nothing — so the solver 'wins' by
    beating no one. Violations are priced instead, giving a real contest.
    """
    gate = baseline_gate(MODEL_A, DEMAND, evaluations=3000)
    assert gate.hill_climb_best < float("inf"), "baseline found no feasible plan"
    assert gate.hill_climb_best < gate.random_best, "climbing beat no better than chance"


# --- Pareto front -----------------------------------------------------------

def test_front_is_ordered_and_trades_cost_against_skill_mix():
    front = pareto_front(MODEL_A, DEMAND)
    assert len(front) >= 3
    costs = [e.daily_cost for e in front]
    shares = [e.rn_share for e in front]
    assert costs == sorted(costs)
    assert shares == sorted(shares), "a dearer plan must buy a richer mix"


def test_front_contains_no_duplicate_points():
    front = pareto_front(MODEL_A, DEMAND)
    points = [(round(e.daily_cost, 6), round(e.rn_share, 6)) for e in front]
    assert len(points) == len(set(points))


def test_dominated_plans_are_discarded():
    def plan(cost, share):
        return Establishment({}, 0.0, share, cost, "Optimal")

    good, dearer_and_leaner = plan(100, 0.7), plan(120, 0.6)
    kept = _non_dominated([good, dearer_and_leaner])
    assert kept == [good]


def test_every_point_on_the_front_is_feasible():
    for e in pareto_front(MODEL_A, DEMAND):
        assert e.status == "Optimal"
        assert e.care_hours >= DEMAND

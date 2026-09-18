"""Tests for the establishment solver, its baselines and the Pareto front."""

import pytest

from app.optimise import (
    DEFAULT_COSTS,
    Establishment,
    _non_dominated,
    annual_cost,
    baseline_gate,
    pareto_front,
    solve,
)
from app.planner import MODEL_A_SHIFTS, MODEL_B_SHIFTS, Model
from app.roles import UK, Role, RoleCatalogue, Task

MODEL_A = Model("Model A", MODEL_A_SHIFTS, 40, {"sn": 8})
MODEL_B = Model("Model B", MODEL_B_SHIFTS, 48, {"sn": 3})
DEMAND = 250.0  # care hours per day, roughly p90 for a 32-bed ward at CMI 1.0


# --- feasibility ------------------------------------------------------------

def test_solver_reaches_a_proven_optimum():
    assert solve(MODEL_A, DEMAND).status == "Optimal"


def test_every_shift_has_a_registered_nurse():
    e = solve(MODEL_A, DEMAND)
    for shift in MODEL_A_SHIFTS:
        assert e.on_shift(shift).get("sn", 0) >= 1, f"{shift} has no registered nurse"


def test_all_task_demand_is_covered():
    e = solve(MODEL_A, DEMAND)
    assert sum(e.hours_by_task().values()) == pytest.approx(DEMAND, rel=1e-3)


def test_night_cover_is_not_sacrificed_to_the_day():
    e = solve(MODEL_A, DEMAND)
    assert sum(e.on_shift("night").values()) >= sum(e.on_shift("early").values()) / 2


# --- scope of practice is structural ----------------------------------------

def test_restricted_tasks_are_never_allocated_to_assistants():
    """The defect this replaces: a cheap, assistant-heavy plan that could not
    actually be delivered, because an HCA may not give medication."""
    e = solve(MODEL_A, DEMAND)
    for (role, task) in e.task_hours:
        assert UK[role].can_cover(Task(task)), f"{role} allocated to {task}"


def test_registered_nurse_share_emerges_from_scope_not_from_a_floor():
    """With no imposed floor the mix is still substantially registered, because
    some work only a registered nurse may do."""
    e = solve(MODEL_A, DEMAND, min_rn_share=0.0)
    assert e.rn_share > 0.25


def test_a_porter_carries_real_hours():
    e = solve(MODEL_A, DEMAND)
    porter = {t: h for (r, t), h in e.task_hours.items() if r == "porter"}
    assert porter, "porter rostered but allocated nothing"
    assert set(porter) <= {"repositioning", "mobility_transfer", "escort_transport"}


def test_a_catalogue_that_cannot_cover_a_task_is_rejected():
    """Better to refuse than to silently produce an undeliverable plan."""
    porters_only = RoleCatalogue(
        jurisdiction="TEST",
        roles={"porter": Role("porter", "Porter",
                              performs=frozenset({Task.ESCORT_TRANSPORT}))},
    )
    with pytest.raises(ValueError, match="undeliverable|may lead"):
        solve(MODEL_A, DEMAND, costs={"porter": 0.3}, catalogue=porters_only)


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
    e = solve(MODEL_B, DEMAND)
    assert not e.compliant
    assert any("night-work default" in b for b in e.breaches)
    assert solve(MODEL_A, DEMAND).compliant


def test_eight_hour_pattern_scores_better_on_wellbeing():
    assert solve(MODEL_A, DEMAND).wellbeing_score > solve(MODEL_B, DEMAND).wellbeing_score


# --- the baseline gate ------------------------------------------------------

def test_solver_beats_both_baselines():
    gate = baseline_gate(MODEL_A, DEMAND, evaluations=2500)
    assert gate.beats_random
    assert gate.beats_hill_climb
    assert gate.passed


def test_the_hill_climber_actually_finds_something():
    """Guards a vacuous gate.

    With infeasible plans scored as infinity the climber has a flat landscape,
    never reaches feasibility, and reports nothing — so the solver 'wins' by
    beating no one. Violations are priced instead, giving a real contest.
    """
    gate = baseline_gate(MODEL_A, DEMAND, evaluations=2500)
    assert gate.hill_climb_best < float("inf"), "baseline found no feasible plan"
    assert gate.hill_climb_best < gate.random_best, "climbing beat no better than chance"


def test_the_baseline_respects_scope_too():
    """A baseline that ignored scope would beat the solver by proposing
    undeliverable plans, and the gate would be meaningless."""
    gate = baseline_gate(MODEL_A, DEMAND, evaluations=1500)
    assert gate.random_best >= solve(MODEL_A, DEMAND).daily_cost


# --- Pareto front -----------------------------------------------------------

def test_front_is_ordered_and_trades_cost_against_skill_mix():
    front = pareto_front(MODEL_A, DEMAND)
    assert len(front) >= 3
    assert [e.daily_cost for e in front] == sorted(e.daily_cost for e in front)
    assert [e.rn_share for e in front] == sorted(e.rn_share for e in front)


def test_the_cheap_end_of_the_front_is_still_deliverable():
    """Previously the low-RN end was untrustworthy: nothing stopped the solver
    assuming assistants could do restricted work."""
    cheapest = pareto_front(MODEL_A, DEMAND)[0]
    for (role, task) in cheapest.task_hours:
        assert UK[role].can_cover(Task(task))


def test_front_contains_no_duplicate_points():
    front = pareto_front(MODEL_A, DEMAND)
    points = [(round(e.daily_cost, 6), round(e.rn_share, 6)) for e in front]
    assert len(points) == len(set(points))


def test_dominated_plans_are_discarded():
    def plan(cost, share):
        return Establishment({}, 0.0, share, cost, "Optimal")

    good, dearer_and_leaner = plan(100, 0.7), plan(120, 0.6)
    assert _non_dominated([good, dearer_and_leaner]) == [good]

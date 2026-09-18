"""Tests for the corrected demand and cost model.

The four `xfail` markers from the characterization pass are gone: those defects
are fixed and the assertions now hold unedited. The three tests that locked in
the *old* inflated outputs (55 SN, 84 SN, single-rounding across shifts) have
been deleted — they existed only to make the fix visible, and keeping them
would pin the bug.
"""

import math

import pytest

from app.planner import (
    MODEL_A_SHIFTS,
    MODEL_B_SHIFTS,
    OVERTIME_DIFFERENTIAL,
    SNCT_UPLIFT,
    Model,
    StaffPlanner,
)

CENSUS = 32
SNCT_BAND = (5.9, 10.2)


@pytest.fixture
def planner():
    return StaffPlanner(unit_census=CENSUS)


# --- shift patterns ---------------------------------------------------------

def test_model_a_shifts_cover_exactly_one_day():
    assert sum(MODEL_A_SHIFTS.values()) == 24


def test_model_b_shifts_cover_exactly_one_day():
    assert sum(MODEL_B_SHIFTS.values()) == 24


def test_a_shift_pattern_that_does_not_tile_a_day_is_rejected():
    with pytest.raises(ValueError, match="must tile a 24h day"):
        Model("bad", {"early": 8, "late": 8, "night": 10}, 40, {"sn": 8})


# --- capacity of one FTE ----------------------------------------------------

def test_availability_comes_from_the_sourced_uplift_alone(planner):
    assert planner.uplift == SNCT_UPLIFT
    assert planner.availability == pytest.approx(1 / 1.22)


def test_vacation_days_are_not_applied_on_top_of_the_uplift(planner):
    """The SNCT uplift already includes annual leave. Applying `vacation_days`
    as well double-counts it — the defect this design replaces."""
    generous = StaffPlanner(unit_census=CENSUS, vacation_days=60)
    assert generous.availability == pytest.approx(planner.availability)


def test_leave_only_uplift_is_reported_and_falls_short(planner):
    result = planner.calculate_model_a()
    assert result["uplift_from_leave_only"] < result["uplift"] == SNCT_UPLIFT


# --- demand -----------------------------------------------------------------

def test_sn_demand_matches_round_the_clock_coverage(planner):
    # 32 beds at 1:8 means 4 nurses on duty at all times, all year.
    fte_hours = planner.productive_hours_per_fte(40)
    expected = math.ceil(4 * 24 * 365 / fte_hours)
    assert planner.calculate_model_a()["needs"]["sn"] == expected


def test_rounding_happens_per_shift_not_once_across_the_day(planner):
    # At 1:7, each shift needs ceil(32/7) = 5. Rounding the day as a whole
    # would give ceil(32/7*3) = 14, i.e. staffing a shift with 4.67 nurses.
    assert planner.staff_on_shift(7) == 5
    assert planner.demand_hours(7, MODEL_A_SHIFTS) == 5 * 24 * 365


def test_demand_scales_with_shift_hours_not_with_shift_count(planner):
    # Both patterns cover 24h, so a role at the same ratio needs the same
    # care hours regardless of how the day is carved up.
    assert planner.demand_hours(8, MODEL_A_SHIFTS) == planner.demand_hours(8, MODEL_B_SHIFTS)


@pytest.mark.parametrize("call", ["calculate_model_a", "calculate_model_b"])
def test_hppd_falls_inside_the_snct_observed_band(planner, call):
    low, high = SNCT_BAND
    hppd = getattr(planner, call)()["hppd"]
    assert low <= hppd <= high, f"{call} HPPD {hppd:.2f} outside SNCT band {SNCT_BAND}"


# --- overtime ---------------------------------------------------------------

def test_overtime_is_dearer_per_hour_than_establishment(planner):
    """The universal invariant. Total cost is a separate question — see below."""
    assert OVERTIME_DIFFERENTIAL > 1


def test_overtime_reduces_the_establishment_it_substitutes_for(planner):
    """`needs` and `costs` must describe the same staffing plan.

    The old model charged overtime on top of an unchanged headcount, so the
    displayed establishment and the displayed cost disagreed about how the
    unit was staffed.
    """
    base = planner.calculate_model_b()["needs"]["sn"]
    with_ot = planner.calculate_model_b(overtime_per_week=10)["needs"]["sn"]
    assert with_ot < base


def test_overtime_cannot_exceed_the_demand_that_exists(planner):
    """Absurd overtime must saturate, not drive regular hours negative."""
    ratios = {"sn": 3, "hca": 16}
    fte_hours = planner.productive_hours_per_fte(48)
    demand = planner.demand_hours(3, MODEL_B_SHIFTS)
    ceiling = demand * (planner.costs["sn"] / fte_hours) * OVERTIME_DIFFERENTIAL

    result = planner.calculate_model_b(ratios=ratios, overtime_per_week=500)
    assert result["needs"]["sn"] == 0          # overtime absorbed all of it
    assert result["costs"]["sn"] == pytest.approx(ceiling)


def test_modest_overtime_costs_more_than_establishment_alone(planner):
    """At the ratio that used to expose the floor-division bug.

    This is deliberately *not* asserted as a universal law. Headcount is lumpy,
    so covering a fractional remainder with overtime can genuinely beat hiring
    a whole person who is idle most of the year. The old failure was different
    in kind: `staff_per_day // 3` discarded staff outright, making overtime
    look ~13% cheaper for a reason that had nothing to do with economics.
    """
    ratios = {"sn": 7, "pn": 12, "hca": 16}
    base = planner.calculate_model_a(ratios=ratios)["costs"]["sn"]
    with_ot = planner.calculate_model_a(
        ratios=ratios, overtime_config={"early": 1, "late": 1, "night": 1}
    )["costs"]["sn"]
    assert with_ot > base


# --- costs ------------------------------------------------------------------

def test_costs_come_from_the_instance_not_from_literals(planner):
    planner.costs = {"sn": 2.0, "pn": 1.0, "hca": 1.0}
    result = planner.calculate_model_a()
    assert result["costs"]["pn"] == pytest.approx(result["needs"]["pn"] * 1.0)


def test_total_cost_is_the_sum_of_its_parts(planner):
    result = planner.calculate_model_a(overtime_config={"early": 1, "late": 1, "night": 1})
    assert result["total_cost"] == pytest.approx(sum(result["costs"].values()))

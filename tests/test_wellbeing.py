"""Tests for the wellbeing index.

Every multiplier asserted here traces to a citation in `research/evidence.db`.
These tests exist to stop the effect sizes drifting: if someone edits a
constant to make a model score better, a test fails and names the source.
"""

import pytest

from app.wellbeing import (
    EWTD_MAX_WEEKLY_HOURS,
    OR_JOB_DISSATISFACTION,
    RR_ERROR_LONG_SHIFT,
    ShiftPattern,
    absence_feedback,
    assess,
    fatigued_fraction,
    sickness_absence_ratio,
)

# Model A: 3 x 8h on a 40h week. Model B: 2 x 12h on a 48h week.
MODEL_A = ShiftPattern(shift_hours=8, weekly_hours=40)
MODEL_B = ShiftPattern(shift_hours=12, weekly_hours=48, night_share=0.5)
REFERENCE = ShiftPattern(shift_hours=8, weekly_hours=37.5, night_share=0.0)


# --- inputs -----------------------------------------------------------------

def test_shares_must_be_fractions():
    with pytest.raises(ValueError, match="night_share"):
        ShiftPattern(8, 40, night_share=1.4)
    with pytest.raises(ValueError, match="rn_share"):
        ShiftPattern(8, 40, rn_share=-0.1)


def test_long_shift_threshold_is_twelve_hours():
    assert not ShiftPattern(11.5, 40).is_long_shift
    assert ShiftPattern(12, 40).is_long_shift


def test_quick_return_threshold_is_eleven_hours():
    assert ShiftPattern(8, 40, min_hours_between_shifts=10).has_quick_returns
    assert not ShiftPattern(8, 40, min_hours_between_shifts=11).has_quick_returns


# --- effect sizes -----------------------------------------------------------

def test_reference_pattern_scores_neutral():
    a = assess(REFERENCE)
    assert a.index == pytest.approx(1.0)
    assert a.score == pytest.approx(100.0)
    assert a.compliant


def test_long_shifts_carry_the_published_odds_ratios():
    a = assess(MODEL_B)
    assert a.components["job_dissatisfaction"] == OR_JOB_DISSATISFACTION
    assert a.components["care_error"] == 1.0, "12.0h is below the 12.5h error threshold"


def test_error_risk_triples_only_past_twelve_and_a_half_hours():
    assert assess(ShiftPattern(12, 48)).components["care_error"] == 1.0
    assert assess(ShiftPattern(12.5, 48)).components["care_error"] == RR_ERROR_LONG_SHIFT


def test_eight_hour_pattern_carries_no_long_shift_penalty():
    a = assess(MODEL_A)
    assert all(
        v == 1.0 for k, v in a.components.items() if k != "sickness_absence"
    )


def test_richer_rn_mix_reduces_sickness_absence():
    """Cost and wellbeing are not purely opposed — a dearer skill mix buys
    back part of its cost through attendance."""
    lean = ShiftPattern(8, 40, rn_share=0.55)
    rich = ShiftPattern(8, 40, rn_share=0.75)
    assert sickness_absence_ratio(rich) < sickness_absence_ratio(lean)


def test_long_shifts_raise_sickness_absence():
    assert sickness_absence_ratio(ShiftPattern(12, 48)) > sickness_absence_ratio(
        ShiftPattern(8, 40)
    )


# --- fatigue ----------------------------------------------------------------

def test_night_work_dominates_the_fatigue_burden():
    """~50x between day and night shifts. Any 24/7 pattern pays this."""
    days_only = ShiftPattern(8, 40, night_share=0.0)
    nights_only = ShiftPattern(8, 40, night_share=1.0)
    assert fatigued_fraction(nights_only) > 50 * fatigued_fraction(days_only)


def test_quick_returns_raise_fatigue_at_equivalent_sleep():
    rested = ShiftPattern(8, 40, min_hours_between_shifts=12)
    rushed = ShiftPattern(8, 40, min_hours_between_shifts=9)
    assert fatigued_fraction(rushed) > fatigued_fraction(rested)


def test_fatigue_never_exceeds_all_working_time():
    worst = ShiftPattern(12, 48, night_share=1.0, max_consecutive_nights=5,
                         min_hours_between_shifts=8)
    assert fatigued_fraction(worst) <= 1.0


# --- hard limits ------------------------------------------------------------

def test_model_b_breaches_the_night_work_default():
    """12h nights against the EWTD 8h night-work default."""
    breaches = assess(MODEL_B).breaches
    assert any("night-work default" in b for b in breaches)


def test_overtime_past_the_weekly_ceiling_is_a_breach():
    a = assess(ShiftPattern(12, 48, overtime_hours_per_week=5))
    assert any("exceed the EWTD" in b for b in a.breaches)


def test_sitting_exactly_at_the_ceiling_is_warned_not_breached():
    a = assess(ShiftPattern(8, EWTD_MAX_WEEKLY_HOURS, night_share=0.0))
    assert a.compliant
    assert any("no legal headroom" in w for w in a.warnings)


def test_three_consecutive_nights_is_a_breach():
    a = assess(ShiftPattern(8, 40, max_consecutive_nights=3))
    assert any("consecutive nights" in b for b in a.breaches)


def test_quick_return_is_a_breach():
    a = assess(ShiftPattern(8, 40, min_hours_between_shifts=9))
    assert any("daily rest minimum" in b for b in a.breaches)


# --- the feedback loop ------------------------------------------------------

def test_understaffing_raises_absence():
    """Absence is endogenous: understaffing raises sickness, which worsens
    understaffing. Treating it as fixed makes a marginal plan look stable."""
    staffed = absence_feedback(0.05, understaffing=0.0, pattern=MODEL_A)
    short = absence_feedback(0.05, understaffing=0.30, pattern=MODEL_A)
    assert short > staffed


def test_long_shifts_raise_absence_beyond_understaffing_alone():
    on_eights = absence_feedback(0.05, 0.2, ShiftPattern(8, 40))
    on_twelves = absence_feedback(0.05, 0.2, ShiftPattern(12, 48))
    assert on_twelves > on_eights


def test_absence_feedback_stays_a_probability():
    assert 0 < absence_feedback(0.05, 5.0, MODEL_B) < 1


def test_absence_feedback_rejects_impossible_rates():
    with pytest.raises(ValueError):
        absence_feedback(1.2, 0.1, MODEL_A)


# --- comparison -------------------------------------------------------------

def test_model_a_outscores_model_b_on_wellbeing():
    """The point of the index. Model B's 12h/48h pattern is dearer in
    wellbeing terms even where it is cheaper in money."""
    assert assess(MODEL_A).score > assess(MODEL_B).score
    assert assess(MODEL_A).compliant
    assert not assess(MODEL_B).compliant

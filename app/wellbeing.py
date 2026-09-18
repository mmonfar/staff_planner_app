"""Staff wellbeing as a measured objective, not a sentiment.

Every multiplier here is an effect size from the literature, recorded with its
citation in `research/evidence.db`. Nothing is invented and nothing is tuned to
make a model look good.

Three findings shape the design:

* **Shift length is the dominant modifiable factor.** Shifts of 12h or more
  raise emotional exhaustion (aOR 1.26), job dissatisfaction (1.40), intention
  to leave (1.29) and sickness absence (1.26), and shifts of 12.5h or more
  triple the odds of a care error. Shift length and overtime act independently,
  so overtime on a long shift compounds rather than substitutes.
* **Night work dwarfs everything else.** Nurses average 5.0h sleep around a
  night shift and spend 51% of it fatigued, against 0.5% on a day shift — a
  ~50x difference. Any 24/7 pattern pays this; the question is how it is spread.
* **Absence is endogenous.** Understaffing raises sickness absence, which
  worsens understaffing. A plan that looks marginally adequate on paper
  degrades in service, so `absence_feedback()` closes that loop explicitly
  instead of treating absence as a fixed input.

Odds ratios for *different outcomes* cannot be meaningfully multiplied into a
probability. `WellbeingAssessment.index` is therefore a ranking device — a
geometric mean of harm ratios — and is documented as such. The component
ratios, which are the defensible numbers, are always reported alongside it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# Threshold at which a shift counts as "long" in the burnout literature.
LONG_SHIFT_HOURS = 12.0
# Separate, higher threshold for the error-risk finding.
ERROR_RISK_HOURS = 12.5

# dallora-2015-bmjopen, adjusted odds ratios, >=12h vs <=8h shifts.
OR_EMOTIONAL_EXHAUSTION = 1.26
OR_DEPERSONALISATION = 1.21
OR_LOW_ACCOMPLISHMENT = 1.39
OR_JOB_DISSATISFACTION = 1.40
OR_INTENTION_TO_LEAVE = 1.29

# dallora-2025-jamanetwopen
OR_SICKNESS_LONG_SHIFTS = 1.26
OR_SICKNESS_PER_10PCT_RN = 0.98

# rogers-2004-healthaff
RR_ERROR_LONG_SHIFT = 3.0

# kim-2026-jonm — fraction of working time spent fatigued.
FATIGUE_DAY = 0.0052
FATIGUE_EVENING = 0.0098
FATIGUE_NIGHT = 0.514
FATIGUE_THREE_NIGHTS = 0.347
QUICK_RETURN_HOURS = 11.0
MAX_SAFE_CONSECUTIVE_NIGHTS = 2

# ewtd-2003-88-ec
EWTD_MAX_WEEKLY_HOURS = 48.0
EWTD_MIN_DAILY_REST = 11.0
EWTD_MAX_NIGHT_HOURS = 8.0

# Reference skill mix the sickness-absence odds ratio is scored against.
REFERENCE_RN_SHARE = 0.55


@dataclass(frozen=True)
class ShiftPattern:
    """How staff actually work, as distinct from how many of them there are."""

    shift_hours: float
    weekly_hours: float
    night_share: float = 1 / 3
    max_consecutive_nights: int = 2
    min_hours_between_shifts: float = 11.0
    overtime_hours_per_week: float = 0.0
    rn_share: float = REFERENCE_RN_SHARE

    def __post_init__(self) -> None:
        if not 0 <= self.night_share <= 1:
            raise ValueError("night_share must be a fraction between 0 and 1")
        if not 0 <= self.rn_share <= 1:
            raise ValueError("rn_share must be a fraction between 0 and 1")

    @property
    def is_long_shift(self) -> bool:
        return self.shift_hours >= LONG_SHIFT_HOURS

    @property
    def has_quick_returns(self) -> bool:
        return self.min_hours_between_shifts < QUICK_RETURN_HOURS

    @property
    def total_weekly_hours(self) -> float:
        return self.weekly_hours + self.overtime_hours_per_week


@dataclass
class WellbeingAssessment:
    components: dict[str, float]
    fatigued_fraction: float
    breaches: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def index(self) -> float:
        """Composite harm ratio: the geometric mean of the component ratios.

        A RANKING DEVICE, not a probability. The components measure different
        outcomes and cannot be combined into one; this exists to order
        candidate patterns, and the components must be shown with it.
        """
        logs = [math.log(v) for v in self.components.values()]
        return math.exp(sum(logs) / len(logs))

    @property
    def score(self) -> float:
        """0-100, where 100 is the reference pattern. Higher is better."""
        return 100 / self.index

    @property
    def compliant(self) -> bool:
        return not self.breaches


def assess(pattern: ShiftPattern) -> WellbeingAssessment:
    """Score a shift pattern against the reference: day shifts of 8h or less,
    no quick returns, at most two consecutive nights, no overtime."""
    long_shift = pattern.is_long_shift

    components = {
        "emotional_exhaustion": OR_EMOTIONAL_EXHAUSTION if long_shift else 1.0,
        "depersonalisation": OR_DEPERSONALISATION if long_shift else 1.0,
        "low_accomplishment": OR_LOW_ACCOMPLISHMENT if long_shift else 1.0,
        "job_dissatisfaction": OR_JOB_DISSATISFACTION if long_shift else 1.0,
        "intention_to_leave": OR_INTENTION_TO_LEAVE if long_shift else 1.0,
        "sickness_absence": sickness_absence_ratio(pattern),
        "care_error": RR_ERROR_LONG_SHIFT if pattern.shift_hours >= ERROR_RISK_HOURS else 1.0,
    }

    assessment = WellbeingAssessment(
        components=components,
        fatigued_fraction=fatigued_fraction(pattern),
    )

    # Hard limits — regulatory or explicitly recommended thresholds.
    if pattern.total_weekly_hours > EWTD_MAX_WEEKLY_HOURS:
        assessment.breaches.append(
            f"weekly hours {pattern.total_weekly_hours:.0f}h exceed the EWTD "
            f"{EWTD_MAX_WEEKLY_HOURS:.0f}h average limit"
        )
    if pattern.min_hours_between_shifts < EWTD_MIN_DAILY_REST:
        assessment.breaches.append(
            f"{pattern.min_hours_between_shifts:.0f}h between shifts is below the "
            f"EWTD {EWTD_MIN_DAILY_REST:.0f}h daily rest minimum, and is a quick "
            "return"
        )
    if pattern.night_share > 0 and pattern.shift_hours > EWTD_MAX_NIGHT_HOURS:
        assessment.breaches.append(
            f"night shifts of {pattern.shift_hours:.0f}h exceed the EWTD "
            f"{EWTD_MAX_NIGHT_HOURS:.0f}h night-work default (derogations may "
            "apply, but must be explicit)"
        )
    if pattern.max_consecutive_nights > MAX_SAFE_CONSECUTIVE_NIGHTS:
        assessment.breaches.append(
            f"{pattern.max_consecutive_nights} consecutive nights exceeds the "
            f"recommended maximum of {MAX_SAFE_CONSECUTIVE_NIGHTS}"
        )

    # Soft signals — real effects that are not rule breaches.
    if long_shift:
        assessment.warnings.append(
            "12h+ shifts: Rogers et al. recommend curtailing routine use and "
            "eliminating the overtime attached to them"
        )
    if pattern.overtime_hours_per_week > 0 and long_shift:
        assessment.warnings.append(
            "overtime on long shifts compounds — shift length and overtime were "
            "found to act independently, so the effects add rather than overlap"
        )
    if pattern.total_weekly_hours == EWTD_MAX_WEEKLY_HOURS:
        assessment.warnings.append(
            "contracted hours sit exactly at the EWTD ceiling, leaving no legal "
            "headroom for overtime"
        )
    return assessment


def sickness_absence_ratio(pattern: ShiftPattern) -> float:
    """Sickness-absence odds relative to the reference pattern.

    Long shifts raise it; a richer registered-nurse mix lowers it. Cost and
    wellbeing are therefore not purely opposed — a more expensive skill mix
    buys back some of its own cost through attendance.
    """
    ratio = OR_SICKNESS_LONG_SHIFTS if pattern.is_long_shift else 1.0
    tenths = (pattern.rn_share - REFERENCE_RN_SHARE) / 0.10
    return ratio * OR_SICKNESS_PER_10PCT_RN**tenths


def fatigued_fraction(pattern: ShiftPattern) -> float:
    """Share of working time spent fatigued, weighted by the night burden."""
    if pattern.max_consecutive_nights >= 3:
        night = FATIGUE_THREE_NIGHTS
    else:
        night = FATIGUE_NIGHT
    day = FATIGUE_DAY if pattern.shift_hours <= 8 else FATIGUE_EVENING
    base = pattern.night_share * night + (1 - pattern.night_share) * day
    # Quick returns raise fatigue at equivalent sleep duration.
    return min(1.0, base * (1.25 if pattern.has_quick_returns else 1.0))


def absence_feedback(base_absence: float, understaffing: float,
                     pattern: ShiftPattern) -> float:
    """Absence rate after the understaffing feedback loop.

    Understaffing raises sickness absence, which deepens the understaffing.
    `understaffing` is the fractional shortfall against required hours (0 when
    fully staffed). Treating absence as exogenous makes a marginal plan look
    stable when it is not.

    The loop is applied once rather than iterated to convergence: the effect
    size is an observed association, and compounding it would extrapolate well
    past what the study measured.
    """
    if not 0 <= base_absence < 1:
        raise ValueError("base_absence must be a fraction below 1")
    understaffing = max(0.0, understaffing)
    # dallora-2025: ~2% higher odds of sickness per 10% understaffing.
    odds = base_absence / (1 - base_absence)
    odds *= 1.02 ** (understaffing / 0.10)
    odds *= sickness_absence_ratio(pattern) / sickness_absence_ratio(
        ShiftPattern(8, pattern.weekly_hours, rn_share=pattern.rn_share)
    )
    return odds / (1 + odds)

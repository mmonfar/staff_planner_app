"""Patient acuity: the primary driver of nursing demand.

Different patients do not require the same nursing time, and the spread is not
marginal. On the Safer Nursing Care Tool ladder a Level 0 patient needs 4.35
hours per patient day and a Level 3 patient needs 26.2 — a **6.0x spread**
(snct-multipliers-nihr, Table 31). The Nursing Activities Score corroborates
this from critical care with a different instrument on another continent:
per-patient nursing time spans 0-176.8% of one nurse's 24-hour day.

This supersedes an earlier conclusion in this project that nursing time was
largely fixed per patient and acuity a weak lever. That came from fitting a
curve inside a single surgical specialty, where the acuity range is narrow by
construction and range restriction flattens the slope. It was an artefact of
the source, not a property of nursing.

Census alone therefore cannot size a ward. Acuity mix does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Hours per patient day by SNCT dependency level, general wards.
# Published multipliers: 0.99 / 1.39 / 1.72 / 1.97 / 5.96 WTE per patient.
SNCT_GENERAL_WARD = {"0": 4.35, "1a": 6.10, "1b": 7.55, "2": 8.65, "3": 26.2}

# Acute admissions units need more at every level below specialling — unit type
# is a second driver alongside acuity.
SNCT_ACUTE_ADMISSIONS = {"0": 5.58, "1a": 7.29, "1b": 9.13, "2": 9.92, "3": 26.2}

LEVELS = ("0", "1a", "1b", "2", "3")

# Ordinal severity, used to tilt the mix as case mix rises.
SEVERITY = {level: rank for rank, level in enumerate(LEVELS)}

# Establishment uplift for annual leave, sickness and training
# (snct-multipliers-nihr). The HPPD figures above EXCLUDE it — they are care
# hours on the day. This resolves the earlier uplift confusion: it supersedes
# both the undecomposed 1.46 rest factor and the app's original 1.087, which
# counted annual leave only.
SNCT_UPLIFT = 0.22

# How sharply the acuity mix tilts toward higher dependency per unit of case
# mix index above 1.0. CALIBRATION KNOB, not a sourced constant: CMI is a DRG
# reimbursement weight and the mapping onto an acuity distribution is local.
# Fit it against your own paired CMI and SNCT observations.
DEFAULT_CMI_TILT = 1.0

# A plausible general-ward starting mix at baseline case complexity. An
# assumption — replace with your ward's own observed census profile.
DEFAULT_BASE_MIX = {"0": 0.30, "1a": 0.35, "1b": 0.20, "2": 0.13, "3": 0.02}


@dataclass(frozen=True)
class AcuityMix:
    """Proportion of patients at each dependency level."""

    proportions: dict[str, float]

    def __post_init__(self) -> None:
        missing = set(LEVELS) - set(self.proportions)
        if missing:
            raise ValueError(f"acuity mix missing levels: {sorted(missing)}")
        total = sum(self.proportions.values())
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"acuity mix sums to {total:.4f}, must sum to 1")

    def hppd(self, ladder: dict[str, float] = None) -> float:
        """Weighted care hours per patient day for this mix."""
        ladder = ladder or SNCT_GENERAL_WARD
        return sum(self.proportions[lvl] * ladder[lvl] for lvl in LEVELS)

    def mean_severity(self) -> float:
        return sum(self.proportions[lvl] * SEVERITY[lvl] for lvl in LEVELS)

    def share_at_or_above(self, level: str) -> float:
        """Proportion needing at least `level` — the high-dependency load."""
        floor = SEVERITY[level]
        return sum(p for lvl, p in self.proportions.items() if SEVERITY[lvl] >= floor)


def mix_from_cmi(
    cmi: float,
    base_mix: dict[str, float] = None,
    tilt: float = DEFAULT_CMI_TILT,
) -> AcuityMix:
    """Shift an acuity mix toward higher dependency as case mix rises.

    Exponential tilting: each level's weight is multiplied by exp(theta *
    severity) and renormalised, where theta scales with CMI above baseline.
    This keeps CMI as the portable, cross-hospital comparable index while
    letting the SNCT ladder — which actually measures nursing time — do the
    work of converting a patient into hours.

    At CMI 1.0 the mix is unchanged. The tilt strength is a local calibration,
    not a published constant.
    """
    base_mix = base_mix or DEFAULT_BASE_MIX
    theta = tilt * (cmi - 1.0)
    weighted = {lvl: base_mix[lvl] * math.exp(theta * SEVERITY[lvl]) for lvl in LEVELS}
    total = sum(weighted.values())
    return AcuityMix({lvl: w / total for lvl, w in weighted.items()})


def demand_hours_per_day(census: int, mix: AcuityMix, ladder: dict[str, float] = None) -> float:
    """Care hours a ward needs in a day. Uplift NOT included — these are hours
    delivered at the bedside, not the establishment required to deliver them."""
    return census * mix.hppd(ladder)


def establishment_hours(care_hours: float, uplift: float = SNCT_UPLIFT) -> float:
    """Contracted hours needed to deliver `care_hours`, after absence."""
    return care_hours * (1 + uplift)

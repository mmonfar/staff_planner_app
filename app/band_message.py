"""Pure helpers for the 'demand outside the SNCT band' message.

No Streamlit here, so the promise in PROJECT_STATUS can be tested. The numbers
come from StochasticPlanner.establishment unchanged.
"""

from __future__ import annotations

from app.stochastic import HPPD_SANITY_BAND


def band_message(hppd_mean: float, census: float) -> str | None:
    """Return the warning text, or None when demand is inside the band."""
    if census <= 0:
        return ("Mean census is 0, so there is no demand to size. "
                "Enter a mean census of 1 or more.")
    low, high = HPPD_SANITY_BAND
    if low <= hppd_mean <= high:
        return None
    return (
        f"Demand is **{hppd_mean:.2f} HPPD**, outside the SNCT observed "
        f"band of {low}–{high} for adult inpatient wards. At this case mix the "
        "ward is no longer a general ward, and general-ward multipliers may not "
        "describe it. Treat the numbers as indicative only."
    )


def ward_band_check(planner, model, policy: float = 0.90, days: int = 10_000) -> dict:
    """Run the planner and pair its result with the band message.

    Census 0 is caught first (the sampler cannot run on it): result is None
    and the message says why.
    """
    if planner.mean_census <= 0:
        return {"result": None, "message": band_message(0.0, 0)}
    result = planner.establishment(model, policy=policy, days=days)
    return {"result": result,
            "message": band_message(result["hppd_mean"], planner.mean_census)}

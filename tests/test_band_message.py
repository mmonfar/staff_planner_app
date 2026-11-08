"""The UI must say so, not silently report a number, when case mix pushes
demand outside the SNCT observed band (PROJECT_STATUS promise).
Synthetic wards only."""

import pytest

from app.band_message import band_message, ward_band_check
from app.planner import MODEL_A_SHIFTS, Model
from app.stochastic import HPPD_SANITY_BAND, StochasticPlanner

MODEL_A = Model("Model A", MODEL_A_SHIFTS, 40, {"sn": 8, "pn": 12, "hca": 16})
LOW, HIGH = 5.9, 10.2


def test_band_is_the_documented_one():
    assert HPPD_SANITY_BAND == (LOW, HIGH)


@pytest.mark.parametrize("hppd,outside", [
    (5.89, True), (5.9, False), (7.0, False), (10.2, False), (10.21, True),
])
def test_message_exactly_at_the_band_edges(hppd, outside):
    msg = band_message(hppd, 32)
    assert (msg is not None) == outside
    if outside:
        assert f"{hppd:.2f} HPPD" in msg
        assert "5.9" in msg and "10.2" in msg


@pytest.mark.parametrize("cmi", [1.0, 1.5, 1.9, 2.0, 2.5, 5.0])
def test_synthetic_wards_by_case_mix(cmi):
    sp = StochasticPlanner(beds=36, mean_census=32, mean_cmi=cmi, seed=3)
    out = ward_band_check(sp, MODEL_A, days=2000)
    hppd = out["result"]["hppd_mean"]
    outside = not (LOW <= hppd <= HIGH)
    assert (out["message"] is not None) == outside
    if outside:
        assert f"{hppd:.2f} HPPD" in out["message"]  # number still shown
    assert out["result"]["hppd_in_band"] == (not outside)


def test_case_mix_20_and_up_is_flagged_and_below_19_is_not():
    flags = {}
    for cmi in (1.0, 1.5, 1.9, 2.0, 2.5):
        sp = StochasticPlanner(beds=36, mean_census=32, mean_cmi=cmi, seed=3)
        flags[cmi] = ward_band_check(sp, MODEL_A, days=2000)["message"] is not None
    assert flags == {1.0: False, 1.5: False, 1.9: False, 2.0: True, 2.5: True}


def test_census_zero_does_not_crash_and_says_why():
    sp = StochasticPlanner(beds=36, mean_census=0, mean_cmi=1.0, seed=3)
    out = ward_band_check(sp, MODEL_A, days=500)
    assert out["result"] is None
    assert "census" in out["message"].lower()
    assert "0" in out["message"]


def test_band_message_with_zero_census_says_why():
    assert "census" in band_message(0.0, 0).lower()

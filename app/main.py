"""Streamlit front end.

The question this app answers is not "what does each model cost" but "does this
ratio actually meet the nursing demand this ward generates". A fixed ratio buys
a fixed number of care hours; patient acuity does not care. The gap between the
two is the output that matters.
"""

import sys
from pathlib import Path

# Fallback for `streamlit run app/main.py` without an editable install
# (`pip install -e .` makes this unnecessary).
sys.path.append(str(Path(__file__).resolve().parent.parent))

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from app.acuity import DEFAULT_BASE_MIX, LEVELS, SNCT_GENERAL_WARD, mix_from_cmi
from app.planner import (
    MODEL_A_SHIFTS,
    MODEL_B_SHIFTS,
    SNCT_UPLIFT,
    Model,
    StaffPlanner,
)
from app.stochastic import HPPD_SANITY_BAND, StochasticPlanner

INK = "#494645"
TEAL = "#0f7d7d"
AMBER = "#c98a1b"
RED = "#b3402f"

st.set_page_config(layout="wide", page_title="Staff Planner", page_icon="📊")

_css = Path(__file__).with_name("styles.css")
if _css.exists():
    st.markdown(f"<style>{_css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

st.title("📊 Staff Planner")
st.caption(
    "Acuity-driven establishment planning. Demand comes from the Safer Nursing "
    "Care Tool ladder; ratios are tested against it, not assumed adequate."
)

# --- inputs -----------------------------------------------------------------

sb = st.sidebar
sb.header("Ward")
with sb.expander("Census and case mix", expanded=True):
    beds = st.number_input("Beds", min_value=1, value=36, step=1)
    mean_census = st.number_input("Mean census", min_value=1, value=32, step=1)
    mean_cmi = st.slider("Case Mix Index", 0.5, 3.0, 1.0, 0.1)
    cmi_sd = st.slider("CMI day-to-day SD", 0.0, 0.5, 0.15, 0.01)
    dispersion = st.slider(
        "Census dispersion (variance ÷ mean)", 1.0, 3.0, 1.6, 0.1,
        help="1.0 is pure Poisson. Real wards are overdispersed — admissions "
             "cluster and discharges batch. Set from your occupancy history.",
    )

with sb.expander("Acuity mapping", expanded=False):
    cmi_tilt = st.slider(
        "CMI → acuity tilt", 0.0, 2.5, 1.0, 0.1,
        help="How sharply the acuity mix shifts up the SNCT ladder as case mix "
             "rises. A local calibration, not a published constant — fit it "
             "against paired CMI and SNCT observations.",
    )
    st.caption("Base mix at CMI 1.0 (assumption — replace with your ward's profile)")
    st.dataframe(
        pd.DataFrame({"level": list(LEVELS),
                      "share": [DEFAULT_BASE_MIX[l] for l in LEVELS],
                      "HPPD": [SNCT_GENERAL_WARD[l] for l in LEVELS]}),
        hide_index=True, use_container_width=True,
    )

with sb.expander("Policy", expanded=True):
    policy = st.slider(
        "Meet demand this often", 0.50, 0.99, 0.90, 0.01,
        help="SNCT modelling found policies meeting demand 90% of the time "
             "gave the best outcomes. Planning to the mean under-delivers by "
             "construction.",
    )
    uplift = st.slider(
        "Establishment uplift", 0.0, 0.50, SNCT_UPLIFT, 0.01,
        help="Annual leave, sickness and training. SNCT uses 22%. This is a "
             "single total — do not add leave separately.",
    )

sb.header("Models")
with sb.expander("Model A — 3 × 8h, 40h week", expanded=True):
    a_sn = st.number_input("SN ratio", min_value=1, value=8, step=1, key="a_sn")
    a_pn = st.number_input("PN ratio", min_value=1, value=12, step=1, key="a_pn")
    a_hca = st.number_input("HCA ratio", min_value=1, value=16, step=1, key="a_hca")
    a_ot = st.number_input("SN overtime h/week", min_value=0, value=0, step=1, key="a_ot")

with sb.expander("Model B — 2 × 12h, 48h week", expanded=True):
    b_sn = st.number_input("SN ratio", min_value=1, value=3, step=1, key="b_sn")
    b_hca = st.number_input("HCA ratio", min_value=1, value=16, step=1, key="b_hca")
    b_ot = st.number_input("SN overtime h/week", min_value=0, value=0, step=1, key="b_ot")

with sb.expander("Relative costs", expanded=False):
    sn_cost = st.number_input("Staff Nurse", min_value=0.0, value=1.0, step=0.05)
    pn_cost = st.number_input("Practical Nurse", min_value=0.0, value=0.65, step=0.05)
    hca_cost = st.number_input("Healthcare Assistant", min_value=0.0, value=0.4, step=0.05)

costs = {"sn": sn_cost, "pn": pn_cost, "hca": hca_cost}
MODEL_A = Model("Model A", MODEL_A_SHIFTS, 40, {"sn": a_sn, "pn": a_pn, "hca": a_hca})
MODEL_B = Model("Model B", MODEL_B_SHIFTS, 48, {"sn": b_sn, "hca": b_hca})

# --- computation -------------------------------------------------------------


@st.cache_data(show_spinner="Simulating demand…")
def run(beds, mean_census, mean_cmi, cmi_sd, dispersion, cmi_tilt, policy,
        ratios, weekly_hours, shifts, days=6000):
    sp = StochasticPlanner(
        beds=beds, mean_census=mean_census, mean_cmi=mean_cmi, cmi_sd=cmi_sd,
        census_dispersion=dispersion, cmi_tilt=cmi_tilt,
    )
    model = Model("m", dict(shifts), weekly_hours, dict(ratios))
    result = sp.establishment(model, policy=policy, days=days)
    result["samples"] = sp.simulate(model, days).samples
    return result


def evaluate(model, overtime_role_hours):
    planner = StaffPlanner(unit_census=mean_census, uplift=uplift, costs=dict(costs))
    return planner.evaluate(model, {"sn": overtime_role_hours} if overtime_role_hours else {})


res_a = run(beds, mean_census, mean_cmi, cmi_sd, dispersion, cmi_tilt, policy,
            tuple(MODEL_A.ratios.items()), 40, tuple(MODEL_A_SHIFTS.items()))
res_b = run(beds, mean_census, mean_cmi, cmi_sd, dispersion, cmi_tilt, policy,
            tuple(MODEL_B.ratios.items()), 48, tuple(MODEL_B_SHIFTS.items()))
cost_a, cost_b = evaluate(MODEL_A, a_ot), evaluate(MODEL_B, b_ot)

# --- verdict -----------------------------------------------------------------

st.subheader("Does the ratio meet demand?")
st.caption(
    f"Acuity-driven demand at the {policy:.0%} percentile, against the care "
    "hours each ratio actually buys."
)

for label, res, cost in (("Model A", res_a, cost_a), ("Model B", res_b, cost_b)):
    gap = res["ratio_gap_hours"]
    cols = st.columns([2, 1, 1, 1, 1])
    if res["ratio_meets_p90_demand"]:
        cols[0].success(f"**{label}** meets demand, +{gap:.0f}h headroom/day")
    else:
        cols[0].error(f"**{label}** SHORT by {abs(gap):.0f} care hours/day")
    cols[1].metric("Demand", f"{res['demand_target']:.0f} h/day",
                   f"{res['mean_vs_target_shortfall']:+.0%} vs mean")
    cols[2].metric("Ratio buys", f"{res['ratio_capacity_hours']:.0f} h/day")
    cols[3].metric("Establishment", f"{res['establishment_fte']} FTE",
                   f"{res['establishment_fte_with_absence'] - res['establishment_fte']:+d} absence")
    cols[4].metric("Relative cost", f"{cost['total_cost']:.1f}")

low, high = HPPD_SANITY_BAND
if not res_a["hppd_in_band"]:
    st.warning(
        f"Demand is **{res_a['hppd_mean']:.2f} HPPD**, outside the SNCT observed "
        f"band of {low}–{high} for adult inpatient wards. At this case mix the "
        "ward is no longer a general ward, and general-ward multipliers may not "
        "describe it. Treat the numbers as indicative only."
    )
if not (res_a["baseline_gate_passed"] and res_b["baseline_gate_passed"]):
    st.error(
        "Baseline gate failed: the simulation diverged from its analytic "
        "approximation by more than 10%. Do not trust these figures."
    )

# --- charts ------------------------------------------------------------------

c1, c2 = st.columns(2)

with c1:
    st.subheader("Demand distribution")
    fig, ax = plt.subplots(figsize=(6, 3.6))
    ax.hist(res_a["samples"], bins=45, color="#d8d5d3", edgecolor="none")
    ax.axvline(res_a["demand_mean"], color=INK, ls="--", lw=1.4,
               label=f"mean {res_a['demand_mean']:.0f}h")
    ax.axvline(res_a["demand_target"], color=RED, lw=1.8,
               label=f"p{policy*100:.0f} {res_a['demand_target']:.0f}h")
    ax.axvline(res_a["ratio_capacity_hours"], color=TEAL, lw=1.8, ls=":",
               label=f"Model A buys {res_a['ratio_capacity_hours']:.0f}h")
    ax.axvline(res_b["ratio_capacity_hours"], color=AMBER, lw=1.8, ls=":",
               label=f"Model B buys {res_b['ratio_capacity_hours']:.0f}h")
    ax.set_xlabel("Care hours required per day", fontsize=8)
    ax.set_ylabel("Days", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=6.5, frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    st.caption(
        "Planning to the mean leaves the ward short on roughly half of all days. "
        "The distance between the dashed and solid lines is what the percentile "
        "policy buys."
    )

with c2:
    st.subheader("Acuity mix at this case mix")
    mix = mix_from_cmi(mean_cmi, tilt=cmi_tilt)
    fig, ax = plt.subplots(figsize=(6, 3.6))
    shares = [mix.proportions[l] for l in LEVELS]
    bars = ax.bar(list(LEVELS), shares, color=[TEAL, "#4a9d9d", AMBER, "#c96b1b", RED])
    for bar, lvl in zip(bars, LEVELS):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.008,
                f"{SNCT_GENERAL_WARD[lvl]:.1f}h", ha="center", fontsize=6.5, color=INK)
    ax.set_xlabel("SNCT dependency level (labels show HPPD)", fontsize=8)
    ax.set_ylabel("Share of patients", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)
    st.caption(
        f"Weighted demand **{mix.hppd():.2f} HPPD**. A Level 3 patient needs "
        f"{SNCT_GENERAL_WARD['3'] / SNCT_GENERAL_WARD['0']:.1f}× the nursing time "
        "of a Level 0 — patients are not interchangeable units of workload."
    )

# --- sensitivity -------------------------------------------------------------

st.subheader("Where each ratio stops coping")
sweep = [round(x * 0.1, 1) for x in range(6, 26)]
rows = []
for cmi in sweep:
    ra = run(beds, mean_census, cmi, cmi_sd, dispersion, cmi_tilt, policy,
             tuple(MODEL_A.ratios.items()), 40, tuple(MODEL_A_SHIFTS.items()), 2500)
    rb = run(beds, mean_census, cmi, cmi_sd, dispersion, cmi_tilt, policy,
             tuple(MODEL_B.ratios.items()), 48, tuple(MODEL_B_SHIFTS.items()), 2500)
    rows.append({"CMI": cmi, "Demand": ra["demand_target"],
                 "Model A": ra["ratio_capacity_hours"], "Model B": rb["ratio_capacity_hours"]})
df = pd.DataFrame(rows)

fig, ax = plt.subplots(figsize=(12, 3.6))
ax.plot(df["CMI"], df["Demand"], color=RED, lw=2, label=f"Demand (p{policy*100:.0f})")
ax.plot(df["CMI"], df["Model A"], color=TEAL, lw=1.6, ls=":", label="Model A capacity")
ax.plot(df["CMI"], df["Model B"], color=AMBER, lw=1.6, ls=":", label="Model B capacity")
ax.fill_between(df["CMI"], df["Model A"], df["Demand"],
                where=df["Demand"] > df["Model A"], color=RED, alpha=0.08)
ax.axvline(mean_cmi, color=INK, lw=0.8, alpha=0.5)
ax.set_xlabel("Case Mix Index", fontsize=8)
ax.set_ylabel("Care hours per day", fontsize=8)
ax.tick_params(labelsize=7)
ax.legend(fontsize=7, frameon=False)
ax.spines[["top", "right"]].set_visible(False)
plt.tight_layout()
st.pyplot(fig)
plt.close(fig)
st.caption(
    "Demand rises with case mix; a fixed ratio does not. Where the red line "
    "crosses a dotted one, that model stops meeting demand — this is the "
    "breakeven that matters, not the cost crossover."
)

# --- provenance --------------------------------------------------------------

with st.expander("Evidence and assumptions"):
    st.markdown(
        f"""
**Sourced** — see `research/SOURCES.md`, regenerate with `python research/ingest.py report`

| Parameter | Value | Source |
|---|---|---|
| SNCT ladder (HPPD) | L0 4.35 → L3 26.2 | NIHR HS&DR 8.16, Table 31 |
| Establishment uplift | {SNCT_UPLIFT:.0%} | SNCT guidance |
| Establishment policy | meet demand 90% of days | NIHR HS&DR 8.16 |
| HPPD observed band | {low}–{high} | NIHR HS&DR 8.16 |
| Mortality per extra patient/nurse | OR 1.068 (1.031–1.106) | Aiken 2014, Lancet 383:1824 |

**Assumptions — not sourced. Calibrate before real use.**
CMI→acuity tilt ({cmi_tilt}), base acuity mix, census dispersion ({dispersion}),
CMI SD ({cmi_sd}).

**Mock data.** No output here is clinically valid until real census, CMI and
acuity observations replace these defaults. Do not present as staffing advice.
"""
    )

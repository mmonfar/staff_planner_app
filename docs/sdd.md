# Staff Planner App - Software Design Document

## Purpose
Answer one question for a ward: does a given staffing ratio meet the nursing demand the ward generates? Demand comes from the Safer Nursing Care Tool (SNCT) acuity ladder and is modelled as a distribution, not a point value (see README).

## Scope
In scope: acuity-driven demand, stochastic establishment sizing, ratio adequacy for two staffing models, a MILP that solves the cheapest compliant staffing, an exact cost / registered-nurse-share Pareto front, scope-of-practice roles by country, a wellbeing index, and a SQLite audit log of runs. Out of scope: real patient data, clinical decisions, staffing advice. Only the UK role catalogue is populated.

Synthetic data only. Not a medical device. Not for clinical decision-making.

## Contract / interfaces
Package `app` (Python). Streamlit front end: `app/main.py`.

- `app.acuity`: `AcuityMix` (`hppd`, `mean_severity`, `share_at_or_above`), `mix_from_cmi`, `demand_hours_per_day`, `establishment_hours`.
- `app.planner`: `Model`, `StaffPlanner` (`availability`, `staff_on_shift`, `demand_hours`, `hours_per_patient_day`, `evaluate`, `calculate_model_a`, `calculate_model_b`).
- `app.stochastic`: `StochasticPlanner` (`simulate`, `ratio_capacity_hours`, `establishment`, `shortfall_risk`), `DemandDistribution`, `acuity_factor`.
- `app.optimise`: `solve`, `annual_cost`, `pareto_front`, `baseline_gate`, `Establishment`, `BaselineResult`.
- `app.roles`: `Task`, `Role`, `RoleCatalogue`, `catalogue(jurisdiction)`, `from_regulator`, `task_demand`.
- `app.wellbeing`: `ShiftPattern`, `assess`, `WellbeingAssessment`, `sickness_absence_ratio`, `fatigued_fraction`, `absence_feedback`.
- `app.audit`: `log_run`, `history`, `evidence_fingerprint`, `add_rationale`, `supersede`, `stale_runs`, `plan_for`.

Run: `streamlit run app/main.py`.

## Acceptance criteria
1. Each public function above returns the documented type for valid input; tests in `tests/` pass.
2. Demand uses the SNCT ladder, so a higher acuity level needs more nursing time (README: L0 4.35 to L3 26.2 HPPD).
3. A jurisdiction without a populated catalogue refuses to plan; it never substitutes UK grades.
4. Every clinical or regulatory constant has a citation (`research/SOURCES.md`); assumptions are marked.
5. Colours in `app/main.py` use brand tokens only (product gate brand linter: 0 findings).

## Tests
Command: `python -m pytest` (run from the repo root).
Last run (7 Nov 2026): 110 passed, 86 warnings, about 15 s.
Files: `test_planner.py`, `test_stochastic.py`, `test_optimise.py`, `test_roles.py`, `test_wellbeing.py`, `test_audit.py`.
README notes that tests marked `xfail` document known defects in the demand formula.

Specs: see `docs/specs/`.

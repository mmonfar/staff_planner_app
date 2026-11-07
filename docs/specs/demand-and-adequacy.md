# Spec: demand and ratio adequacy
Problem: a fixed ratio buys fixed care hours; acuity varies. We need to show the gap.
Acceptance criteria:
- `StochasticPlanner.establishment` sizes demand at a chosen percentile (default 0.90).
- `StaffPlanner.evaluate` compares each `Model` capacity with that demand.
- `mix_from_cmi` shifts the acuity mix with case-mix index.
Tests: `tests/test_planner.py`, `tests/test_stochastic.py` (`python -m pytest`).

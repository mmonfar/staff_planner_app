# Spec: solved establishment and Pareto front
Problem: ratios should be an output, not an input.
Acceptance criteria:
- `solve` returns the cheapest staffing that meets demand and the minimum registered-nurse share.
- Roles only cover tasks they are permitted to do (`app.roles`).
- `pareto_front` traces cost against registered-nurse share; `baseline_gate` checks the solver baseline.
- An unpopulated country catalogue refuses to plan.
Tests: `tests/test_optimise.py`, `tests/test_roles.py` (`python -m pytest`).

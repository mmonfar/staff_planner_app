# Spec: audit log and wellbeing index
Problem: runs must be traceable; shift patterns must be checked for fatigue and working-time breaches.
Acceptance criteria:
- `log_run` stores a run with an evidence fingerprint; `history` and `stale_runs` read it back.
- `assess` returns a wellbeing index and a `compliant` flag for a `ShiftPattern`.
Tests: `tests/test_audit.py`, `tests/test_wellbeing.py` (`python -m pytest`).

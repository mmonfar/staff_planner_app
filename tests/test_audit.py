"""Tests for the staffing-decision audit trail."""

import json

import pytest

from app.audit import (
    add_rationale,
    connect,
    evidence_fingerprint,
    history,
    log_run,
    plan_for,
    stale_runs,
    supersede,
)
from app.optimise import solve
from app.planner import MODEL_A_SHIFTS, Model

MODEL_A = Model("Model A", MODEL_A_SHIFTS, 40, {"sn": 8, "pn": 12, "hca": 16})
DEMAND = 250.0
SCENARIO = {"beds": 36, "mean_census": 32, "mean_cmi": 1.0, "policy": 0.90}


@pytest.fixture
def db(tmp_path):
    return tmp_path / "planning_log.db"


@pytest.fixture
def establishment():
    return solve(MODEL_A, DEMAND)


# --- recording --------------------------------------------------------------

def test_a_run_records_the_plan_and_the_scenario(db, establishment):
    logged = log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90, path=db)
    rows = history(path=db)
    assert len(rows) == 1
    row = rows[0]
    assert row["model"] == "Model A"
    assert json.loads(row["scenario"]) == SCENARIO
    assert row["daily_cost"] == pytest.approx(establishment.daily_cost)


def test_the_plan_is_recoverable_shift_by_shift(db, establishment):
    logged = log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90, path=db)
    plan = plan_for(logged.run_id, path=db)
    assert set(plan) <= set(MODEL_A_SHIFTS)
    for shift, roles in plan.items():
        assert roles.get("sn", 0) >= 1, f"{shift} recorded without a registered nurse"


def test_compliance_and_gate_status_are_recorded(db, establishment):
    """Nobody should have to take on trust that the checks passed."""
    log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90,
            baseline_gate_passed=True, path=db)
    row = history(path=db)[0]
    assert row["compliant"] == 1
    assert row["baseline_gate_passed"] == 1
    assert row["solver_status"] == "Optimal"


def test_breaches_are_stored_not_dropped(db):
    from app.planner import MODEL_B_SHIFTS
    model_b = Model("Model B", MODEL_B_SHIFTS, 48, {"sn": 3, "hca": 16})
    log_run(solve(model_b, DEMAND), "Model B", SCENARIO, DEMAND, 0.90, path=db)
    row = history(path=db)[0]
    assert row["compliant"] == 0
    assert json.loads(row["breaches"]), "a non-compliant plan logged with no breaches"


# --- evidence fingerprint ---------------------------------------------------

def test_fingerprint_is_stable_across_calls():
    assert evidence_fingerprint() == evidence_fingerprint()


def test_fingerprint_tracks_parameter_values_not_the_file(tmp_path):
    """Regenerating the store without changing a number must not invalidate
    past decisions — the question is whether the evidence moved, not the file."""
    import sqlite3
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    for path in (a, b):
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE sources (id INTEGER PRIMARY KEY, slug TEXT)")
            c.execute("CREATE TABLE parameters (id INTEGER PRIMARY KEY, key TEXT,"
                      " value TEXT, binding TEXT, source_id INTEGER)")
            c.execute("INSERT INTO sources VALUES (1, 'snct')")
            c.execute("INSERT INTO parameters VALUES (1, 'uplift', '0.22', 'soft', 1)")
    assert evidence_fingerprint(a) == evidence_fingerprint(b)


def test_changing_a_parameter_changes_the_fingerprint(tmp_path):
    import sqlite3
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    for path, value in ((a, "0.22"), (b, "0.30")):
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE sources (id INTEGER PRIMARY KEY, slug TEXT)")
            c.execute("CREATE TABLE parameters (id INTEGER PRIMARY KEY, key TEXT,"
                      " value TEXT, binding TEXT, source_id INTEGER)")
            c.execute("INSERT INTO sources VALUES (1, 'snct')")
            c.execute("INSERT INTO parameters VALUES (1, 'uplift', ?, 'soft', 1)", (value,))
    assert evidence_fingerprint(a) != evidence_fingerprint(b)


def test_missing_evidence_store_is_reported_not_crashed(tmp_path):
    assert evidence_fingerprint(tmp_path / "absent.db") == "no-evidence-store"


def test_runs_under_older_evidence_are_flagged_stale(db, establishment):
    log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90, path=db)
    with connect(db) as conn:
        conn.execute("UPDATE runs SET evidence_fingerprint = 'older'")
    assert len(stale_runs(path=db)) == 1
    assert history(path=db)[0]["stale"]


# --- rationale and supersession ---------------------------------------------

def test_rationale_can_be_attached_after_the_fact(db, establishment):
    logged = log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90, path=db)
    add_rationale(logged.run_id, "chose the 64% point for night cover", author="DoN",
                  path=db)
    with connect(db) as conn:
        notes = conn.execute("SELECT * FROM rationale WHERE run_id = ?",
                             (logged.run_id,)).fetchall()
    assert len(notes) == 1
    assert notes[0]["author"] == "DoN"


def test_superseding_keeps_the_original(db, establishment):
    """A reversed staffing decision is part of the record, not an
    embarrassment to be deleted."""
    first = log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90, path=db)
    second = log_run(establishment, "Model A", SCENARIO, DEMAND, 0.95, path=db)
    supersede(first.run_id, second.run_id, path=db)

    rows = {r["id"]: r for r in history(path=db)}
    assert len(rows) == 2, "superseding deleted the original"
    assert rows[first.run_id]["superseded_by"] == second.run_id
    assert rows[second.run_id]["superseded_by"] is None


def test_a_run_cannot_supersede_itself(db, establishment):
    logged = log_run(establishment, "Model A", SCENARIO, DEMAND, 0.90, path=db)
    with pytest.raises(ValueError):
        supersede(logged.run_id, logged.run_id, path=db)


def test_history_is_newest_first(db, establishment):
    for policy in (0.80, 0.90, 0.95):
        log_run(establishment, "Model A", SCENARIO, DEMAND, policy, path=db)
    assert [r["policy"] for r in history(path=db)] == [0.95, 0.90, 0.80]

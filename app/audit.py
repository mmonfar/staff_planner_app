"""An audit trail for staffing decisions.

The evidence store records *what the literature says*. The brain ledger records
*why we chose a method*. Neither records what this app actually recommended, to
whom, on what inputs — and that is the record anyone challenging a roster will
ask for.

Every solved establishment is written here with:

* the full scenario that produced it, so it can be re-run exactly;
* an **evidence fingerprint** — a hash over the parameter table of
  `research/evidence.db`. If a multiplier or limit later changes, plans made
  under the old evidence are visibly stale rather than silently wrong;
* the baseline-gate and compliance status at the time, so nobody has to take on
  trust that the checks passed;
* an optional rationale, for the part a solver cannot supply: why this point on
  the Pareto front and not another.

Superseding rather than deleting is deliberate. A staffing decision that was
later reversed is part of the record, not an embarrassment to be tidied away.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "research" / "planning_log.db"
EVIDENCE_PATH = Path(__file__).resolve().parent.parent / "research" / "evidence.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id                   INTEGER PRIMARY KEY,
    ran_at               TEXT NOT NULL,
    label                TEXT,
    model                TEXT NOT NULL,
    scenario             TEXT NOT NULL,   -- JSON: every input needed to re-run
    demand_target        REAL NOT NULL,
    policy               REAL NOT NULL,
    daily_cost           REAL NOT NULL,
    rn_share             REAL NOT NULL,
    wellbeing_score      REAL,
    compliant            INTEGER NOT NULL,
    breaches             TEXT,
    solver_status        TEXT,
    baseline_gate_passed INTEGER,
    evidence_fingerprint TEXT NOT NULL,
    superseded_by        INTEGER REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS plan_lines (
    id        INTEGER PRIMARY KEY,
    run_id    INTEGER NOT NULL REFERENCES runs(id),
    shift     TEXT NOT NULL,
    role      TEXT NOT NULL,
    headcount INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rationale (
    id       INTEGER PRIMARY KEY,
    run_id   INTEGER NOT NULL REFERENCES runs(id),
    author   TEXT,
    noted_at TEXT NOT NULL,
    note     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_ran_at ON runs(ran_at);
CREATE INDEX IF NOT EXISTS idx_plan_lines_run ON plan_lines(run_id);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def evidence_fingerprint(path: Path = EVIDENCE_PATH) -> str:
    """Hash of every parameter value and its source.

    Keyed on the parameters themselves rather than the file, so regenerating
    the database without changing a number keeps the fingerprint stable — the
    question being answered is "was this plan made under the same evidence",
    not "is this the same file".
    """
    if not path.exists():
        return "no-evidence-store"
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT p.key, p.value, p.binding, s.slug FROM parameters p "
            "LEFT JOIN sources s ON s.id = p.source_id ORDER BY p.key"
        ).fetchall()
    digest = hashlib.sha256()
    for row in rows:
        digest.update("\x1f".join(str(c) for c in row).encode("utf-8"))
    return digest.hexdigest()[:16]


@dataclass
class LoggedRun:
    run_id: int
    fingerprint: str
    stale: bool = False


def log_run(
    establishment,
    model_name: str,
    scenario: dict,
    demand_target: float,
    policy: float,
    baseline_gate_passed: bool | None = None,
    label: str = None,
    rationale: str = None,
    author: str = None,
    path: Path = DB_PATH,
) -> LoggedRun:
    """Record one solved establishment. Returns its id and fingerprint."""
    fingerprint = evidence_fingerprint()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO runs (ran_at, label, model, scenario, demand_target, policy,"
            " daily_cost, rn_share, wellbeing_score, compliant, breaches, solver_status,"
            " baseline_gate_passed, evidence_fingerprint)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                now, label, model_name, json.dumps(scenario, sort_keys=True),
                demand_target, policy, establishment.daily_cost,
                establishment.rn_share, establishment.wellbeing_score,
                int(establishment.compliant), json.dumps(list(establishment.breaches)),
                establishment.status,
                None if baseline_gate_passed is None else int(baseline_gate_passed),
                fingerprint,
            ),
        )
        run_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO plan_lines (run_id, shift, role, headcount) VALUES (?,?,?,?)",
            [(run_id, s, r, n) for (r, s), n in establishment.headcount.items() if n],
        )
        if rationale:
            conn.execute(
                "INSERT INTO rationale (run_id, author, noted_at, note) VALUES (?,?,?,?)",
                (run_id, author, now, rationale),
            )
    return LoggedRun(run_id=run_id, fingerprint=fingerprint)


def add_rationale(run_id: int, note: str, author: str = None, path: Path = DB_PATH) -> None:
    """Attach the reasoning a solver cannot supply — why this point, not another."""
    with connect(path) as conn:
        conn.execute(
            "INSERT INTO rationale (run_id, author, noted_at, note) VALUES (?,?,?,?)",
            (run_id, author,
             datetime.now(timezone.utc).isoformat(timespec="seconds"), note),
        )


def supersede(old_run_id: int, new_run_id: int, path: Path = DB_PATH) -> None:
    """Mark a decision as replaced. The original stays: a reversed staffing
    decision is part of the record, not something to delete."""
    if old_run_id == new_run_id:
        raise ValueError("a run cannot supersede itself")
    with connect(path) as conn:
        conn.execute("UPDATE runs SET superseded_by = ? WHERE id = ?",
                     (new_run_id, old_run_id))


def history(limit: int = 50, path: Path = DB_PATH) -> list[sqlite3.Row]:
    """Recent runs, newest first, each flagged if the evidence has since moved."""
    current = evidence_fingerprint()
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r, stale=r["evidence_fingerprint"] != current) for r in rows]


def stale_runs(path: Path = DB_PATH) -> list[dict]:
    """Plans made under evidence that has since changed.

    These are not wrong, but they were decided on different numbers and should
    be re-run before anyone relies on them again.
    """
    return [r for r in history(limit=10_000, path=path) if r["stale"]]


def plan_for(run_id: int, path: Path = DB_PATH) -> dict[str, dict[str, int]]:
    with connect(path) as conn:
        rows = conn.execute(
            "SELECT shift, role, headcount FROM plan_lines WHERE run_id = ?", (run_id,)
        ).fetchall()
    plan: dict[str, dict[str, int]] = {}
    for row in rows:
        plan.setdefault(row["shift"], {})[row["role"]] = row["headcount"]
    return plan

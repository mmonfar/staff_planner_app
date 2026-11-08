"""Status check. Exit 1 if a task id is in both the Pending and Done tables
of PROJECT_STATUS.md, or if a test count in README.md or PROJECT_STATUS.md
differs from the pytest count. Counts are written as `Tests: N passing`.
Run from the repo root: python tests/check_status_ids.py
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def table_ids(text, heading):
    """Task ids (first column) of the table under `## heading`."""
    m = re.search(rf"^## {heading}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if not m:
        return None
    return set(re.findall(r"^\|\s*(\d+)\s*\|", m.group(1), re.M))


def pytest_count():
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT, capture_output=True, text=True).stdout
    m = re.search(r"(\d+) tests? collected", out) or re.search(r"^(\d+) tests?", out, re.M)
    return int(m.group(1)) if m else None


def main():
    fails = []
    status = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    done, pending = table_ids(status, "Done"), table_ids(status, "Pending")
    if done is None or pending is None:
        fails.append("Done or Pending table not found")
    else:
        both = sorted(done & pending, key=int)
        if both:
            fails.append(f"task ids in both tables: {', '.join(both)}")
    real = pytest_count()
    if real is None:
        fails.append("could not read pytest count")
    for name in ("README.md", "PROJECT_STATUS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        counts = re.findall(r"Tests:\s*(\d+) passing", text)
        if not counts:
            fails.append(f"{name}: no 'Tests: N passing' line")
        for c in counts:
            if real is not None and int(c) != real:
                fails.append(f"{name}: says {c}, pytest has {real}")
    for f in fails:
        print("FAIL:", f)
    if not fails:
        print(f"OK: no id in both tables; test count {real} matches")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())

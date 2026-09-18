"""Populate and query the evidence store.

    python research/ingest.py seed      # load the researched sources/parameters
    python research/ingest.py report    # regenerate research/SOURCES.md
    python research/ingest.py get KEY   # resolve one parameter with its citation
"""
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).with_name("evidence.db")


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
    return c


def get(key):
    """Resolve a parameter to (value, citation). Used by the model code."""
    with connect() as c:
        row = c.execute(
            "SELECT p.*, s.slug, s.title, s.url, s.year FROM parameters p "
            "LEFT JOIN sources s ON s.id = p.source_id WHERE p.key = ?", (key,)
        ).fetchone()
    if row is None:
        raise KeyError(f"no parameter {key!r} in evidence store")
    return row


def report():
    with connect() as c:
        srcs = c.execute("SELECT * FROM sources ORDER BY publisher, year").fetchall()
        params = c.execute(
            "SELECT p.*, s.slug FROM parameters p LEFT JOIN sources s ON s.id=p.source_id "
            "ORDER BY p.kind, p.key").fetchall()
        rets = c.execute("SELECT * FROM retrievals ORDER BY ran_at, id").fetchall()

    L = ["# Evidence Register", "",
         "**Generated from `research/evidence.db` — do not edit by hand.**",
         "Regenerate with `python research/ingest.py report`.", "",
         "## Parameters", "",
         "| key | value | unit | binding | confidence | source |",
         "|---|---|---|---|---|---|"]
    for p in params:
        L.append(f"| `{p['key']}` | {p['value']} | {p['unit'] or ''} | {p['binding'] or ''} "
                 f"| {p['confidence']} | {p['slug'] or '—'} |")

    L += ["", "## Sources", ""]
    for s in srcs:
        L.append(f"### `{s['slug']}`")
        L.append(f"- **{s['title']}**")
        L.append(f"- {s['publisher'] or '?'} · {s['year'] or '?'} · {s['jurisdiction'] or '?'} "
                 f"· {s['doc_type'] or '?'}")
        L.append(f"- <{s['url']}>")
        L.append(f"- retrieved {s['retrieved_at'] or 'n/a'} via {s['retrieval']}")
        if s["notes"]:
            L.append(f"- {s['notes']}")
        L.append("")

    L += ["## Retrieval log", "",
          "Every query run, including the ones that returned nothing — so gaps are",
          "visible rather than silently missing.", "",
          "| ran | tool | query | result |", "|---|---|---|---|"]
    for r in rets:
        L.append(f"| {r['ran_at']} | {r['tool']} | {r['query']} | {r['result_note']} |")

    Path(__file__).with_name("SOURCES.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"SOURCES.md: {len(srcs)} sources, {len(params)} parameters, {len(rets)} retrievals")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "seed":
        import seed_data
        seed_data.seed(connect())
        report()
    elif cmd == "get":
        r = get(sys.argv[2])
        print(f"{r['key']} = {r['value']} {r['unit'] or ''}  [{r['slug']}] {r['url']}")
    else:
        report()

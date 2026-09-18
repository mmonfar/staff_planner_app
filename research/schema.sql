-- Evidence store for staff_planner_app.
-- SQLite over markdown: model code resolves parameters by key at runtime, which
-- a prose file cannot do. SOURCES.md is GENERATED from this db for git review.
-- Mirrors the refs_books brain.db pattern (db of record + generated view).

CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY,
    slug          TEXT UNIQUE NOT NULL,   -- stable citation key, e.g. 'nice-sg1-2014'
    title         TEXT NOT NULL,
    publisher     TEXT,                   -- NICE, CMS, RCN, EU, ...
    year          INTEGER,
    jurisdiction  TEXT,                   -- UK, US, EU, INTL
    doc_type      TEXT,                   -- guideline | statute | standard | study | reference
    url           TEXT,
    retrieved_at  TEXT,                   -- ISO date the URL was actually fetched
    retrieval     TEXT,                   -- 'web' | 'brain' | 'unverified'
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS parameters (
    id          INTEGER PRIMARY KEY,
    key         TEXT UNIQUE NOT NULL,     -- model-facing name, e.g. 'hppd.med_surg.base'
    value       TEXT NOT NULL,            -- kept TEXT: some params are ranges/expressions
    unit        TEXT,
    applies_to  TEXT,                     -- unit type / role / shift this constrains
    kind        TEXT,                     -- demand | skillmix | wellbeing | cost | acuity
    binding     TEXT,                     -- 'hard' (regulatory) | 'soft' (guidance) | 'default'
    source_id   INTEGER REFERENCES sources(id),
    quote       TEXT,                     -- short supporting quote, <15 words, attributed
    confidence  TEXT,                     -- verified | partial | unverified
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS retrievals (
    id          INTEGER PRIMARY KEY,
    query       TEXT NOT NULL,
    tool        TEXT,                     -- WebSearch | WebFetch | brain_search
    ran_at      TEXT NOT NULL,
    result_note TEXT                      -- what was found, or 'no usable result'
);

CREATE INDEX IF NOT EXISTS idx_param_kind ON parameters(kind);
CREATE INDEX IF NOT EXISTS idx_param_source ON parameters(source_id);

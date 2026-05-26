-- Container service tables.
-- Additive only: no modifications to team_*, netdef_*, money_*, judge_*.
-- Loaded after schema.sql by shared/bootstrap.py.

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- container_* : the 1B-MNT fill monitor
------------------------------------------------------------

-- One global container per system. The constant target lives in
-- shared/constants.py, but the row exists so witness log can target it.
CREATE TABLE IF NOT EXISTS container_state (
    id            TEXT PRIMARY KEY,                       -- UUID7
    target_mnt    INTEGER NOT NULL,                       -- frozen, matches CONTAINER_TARGET
    started_at    TEXT NOT NULL,
    ends_at       TEXT NOT NULL,
    monitor_id    TEXT REFERENCES team_workers(id),       -- the one agent
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every inflow that fills the container. Channel + linkage to a milestone
-- (optional). The container service appends here; nothing else writes.
-- Negative amounts allowed for refunds; sum() across this table is the
-- live fill level.
CREATE TABLE IF NOT EXISTS container_inflows (
    id            TEXT PRIMARY KEY,                       -- UUID7
    occurred_at   TEXT NOT NULL,                          -- when the cash actually moved
    amount_mnt    REAL NOT NULL,                          -- positive = inflow, negative = refund
    channel       TEXT NOT NULL,                          -- one of CHANNELS in constants.py
    milestone_id  TEXT,                                   -- optional: M01..M27 (no FK; const string)
    note          TEXT,
    source        TEXT NOT NULL CHECK (source IN ('manual','excel','api','agent')) DEFAULT 'manual',
    recorded_by   TEXT REFERENCES team_workers(id),
    recorded_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_inflows_occurred ON container_inflows(occurred_at);
CREATE INDEX IF NOT EXISTS idx_inflows_milestone ON container_inflows(milestone_id);

-- Milestone progress snapshots. The actual milestone DEFINITIONS are
-- frozen in constants.py; this table tracks per-milestone runtime state.
-- One row per milestone_id. Created at seed; updated by the container
-- agent or by direct status updates.
CREATE TABLE IF NOT EXISTS container_milestone_progress (
    milestone_id    TEXT PRIMARY KEY,                     -- M01..M27 from constants.py
    status          TEXT NOT NULL CHECK (status IN ('pending','in_progress','done','blocked','missed')) DEFAULT 'pending',
    completion_pct  REAL NOT NULL DEFAULT 0 CHECK (completion_pct BETWEEN 0 AND 100),
    actual_revenue_mnt REAL NOT NULL DEFAULT 0,
    completed_at    TEXT,
    notes           TEXT,
    updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by      TEXT REFERENCES team_workers(id)
);

-- Scenario snapshots. Each /scenarios/simulate POST stores its result
-- so audits can compare projection vs reality later.
CREATE TABLE IF NOT EXISTS container_scenario_runs (
    id            TEXT PRIMARY KEY,
    scenario_key  TEXT NOT NULL CHECK (scenario_key IN ('bear','base','bull')),
    inputs_json   TEXT NOT NULL,
    output_json   TEXT NOT NULL,
    total_revenue_mnt REAL NOT NULL,
    goal_pct      REAL NOT NULL,
    a_profit_mnt  REAL NOT NULL,
    b_profit_mnt  REAL NOT NULL,
    run_at        TEXT NOT NULL DEFAULT (datetime('now')),
    run_by        TEXT REFERENCES team_workers(id)
);

-- Excel sync log. Every import/export gets a row.
CREATE TABLE IF NOT EXISTS container_excel_sync (
    id            TEXT PRIMARY KEY,
    direction     TEXT NOT NULL CHECK (direction IN ('import','export')),
    rows_count    INTEGER NOT NULL,
    bytes         INTEGER,
    sha256        TEXT,                                   -- hex
    note          TEXT,
    actor_id      TEXT REFERENCES team_workers(id),
    occurred_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

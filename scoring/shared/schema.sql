-- Single scoring.db, schema-prefixed tables for four services.
-- Every primary key and foreign key is a UUID7 string (TEXT).
-- UUID7 sorts lexicographically in creation-time order, so it doubles
-- as a chronological cursor without needing a separate auto-increment.
-- Read order: team -> netdef -> money -> judge.

PRAGMA foreign_keys = ON;

------------------------------------------------------------
-- team_*  : Startup team management
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS team_workers (
    id              TEXT PRIMARY KEY,                       -- UUID7
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('human','agent')),
    handle          TEXT NOT NULL UNIQUE,
    base_salary     REAL NOT NULL DEFAULT 0,
    salary_currency TEXT NOT NULL DEFAULT 'USD',
    hired_at        TEXT NOT NULL DEFAULT (datetime('now')),
    active          INTEGER NOT NULL DEFAULT 1,
    password_hash   TEXT,                                   -- NULL = no login, can be acted-as
    is_admin        INTEGER NOT NULL DEFAULT 0
);

-- Sessions: server-issued cookie token mapped to a worker. UUID7 token doubles
-- as a cursor; expires_at is checked on each lookup.
CREATE TABLE IF NOT EXISTS team_sessions (
    token       TEXT PRIMARY KEY,
    worker_id   TEXT NOT NULL REFERENCES team_workers(id) ON DELETE CASCADE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL,
    user_agent  TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_worker ON team_sessions(worker_id);

CREATE TABLE IF NOT EXISTS team_skills (
    id          TEXT PRIMARY KEY,
    worker_id   TEXT NOT NULL REFERENCES team_workers(id) ON DELETE CASCADE,
    skill_name  TEXT NOT NULL,
    level       INTEGER NOT NULL CHECK (level BETWEEN 0 AND 100),
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS team_projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    description TEXT,
    started_at  TEXT NOT NULL DEFAULT (datetime('now')),
    status      TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS team_tasks (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES team_projects(id) ON DELETE CASCADE,
    title        TEXT NOT NULL,
    description  TEXT,
    weight       INTEGER NOT NULL CHECK (weight BETWEEN 1 AND 10),
    assignee_id  TEXT REFERENCES team_workers(id),
    status       TEXT NOT NULL CHECK (status IN ('open','in_progress','done','cancelled','stock','danger')) DEFAULT 'open',
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    created_by   TEXT REFERENCES team_workers(id)
);

CREATE TABLE IF NOT EXISTS team_kpis (
    id          TEXT PRIMARY KEY,
    scope       TEXT NOT NULL CHECK (scope IN ('worker','team','project')),
    scope_id    TEXT NOT NULL,           -- free-form: worker UUID, team label, or project UUID
    period      TEXT NOT NULL,
    metric      TEXT NOT NULL,
    value       REAL NOT NULL,
    target      REAL NOT NULL,
    score       REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS team_performance_scores (
    id              TEXT PRIMARY KEY,
    worker_id       TEXT NOT NULL REFERENCES team_workers(id) ON DELETE CASCADE,
    period          TEXT NOT NULL,
    score           REAL NOT NULL,
    components_json TEXT NOT NULL,
    computed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

------------------------------------------------------------
-- netdef_* : Network defense (peer review)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS netdef_peer_scores (
    id             TEXT PRIMARY KEY,
    scorer_id      TEXT NOT NULL REFERENCES team_workers(id),
    target_task_id TEXT NOT NULL REFERENCES team_tasks(id),
    score          INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    was_unfinished INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS netdef_comments (
    id          TEXT PRIMARY KEY,
    author_id   TEXT NOT NULL REFERENCES team_workers(id),
    target_type TEXT NOT NULL CHECK (target_type IN ('task','worker','transaction','meeting')),
    target_id   TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS netdef_mentions (
    id                   TEXT PRIMARY KEY,
    comment_id           TEXT NOT NULL REFERENCES netdef_comments(id) ON DELETE CASCADE,
    mentioned_worker_id  TEXT NOT NULL REFERENCES team_workers(id)
);

------------------------------------------------------------
-- money_* : Money management with binding votes
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS money_meetings (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    agenda       TEXT,
    scheduled_at TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('scheduled','open','closed')) DEFAULT 'scheduled'
);

CREATE TABLE IF NOT EXISTS money_votes (
    id                    TEXT PRIMARY KEY,
    meeting_id            TEXT NOT NULL REFERENCES money_meetings(id) ON DELETE CASCADE,
    proposal_text         TEXT NOT NULL,
    quorum_required       INTEGER NOT NULL,
    majority_threshold    REAL NOT NULL DEFAULT 0.5,
    status                TEXT NOT NULL CHECK (status IN ('open','passed','failed','expired')) DEFAULT 'open',
    opened_at             TEXT NOT NULL DEFAULT (datetime('now')),
    closed_at             TEXT,
    linked_transaction_id TEXT
);

CREATE TABLE IF NOT EXISTS money_ballots (
    id        TEXT PRIMARY KEY,
    vote_id   TEXT NOT NULL REFERENCES money_votes(id) ON DELETE CASCADE,
    voter_id  TEXT NOT NULL REFERENCES team_workers(id),
    choice    TEXT NOT NULL CHECK (choice IN ('yes','no','abstain')),
    cast_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(vote_id, voter_id)
);

CREATE TABLE IF NOT EXISTS money_transactions (
    id               TEXT PRIMARY KEY,
    occurred_at      TEXT NOT NULL,
    amount           REAL NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'USD',
    sender_party     TEXT NOT NULL,
    receiver_party   TEXT NOT NULL,
    location         TEXT,
    payment_method   TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('deposit','withdrawal','refund','transfer','loan_payment')),
    status           TEXT NOT NULL CHECK (status IN ('pending_vote','committed','rejected')) DEFAULT 'pending_vote',
    vote_id          TEXT REFERENCES money_votes(id),
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS money_reports (
    id           TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    report_type  TEXT NOT NULL,
    period       TEXT NOT NULL,
    data_json    TEXT NOT NULL
);

------------------------------------------------------------
-- judge_* : Smart Judge (audit + witness)
------------------------------------------------------------
CREATE TABLE IF NOT EXISTS judge_witness_log (
    id           TEXT PRIMARY KEY,             -- UUID7: lex-sorts by emit time
    ts           TEXT NOT NULL DEFAULT (datetime('now')),
    actor_id     TEXT,
    service      TEXT NOT NULL,
    action       TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    target_id    TEXT,
    payload_json TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_hash    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS judge_anomaly_rules (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    rule_type   TEXT NOT NULL,
    params_json TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS judge_anomalies (
    id            TEXT PRIMARY KEY,
    rule_id       TEXT NOT NULL REFERENCES judge_anomaly_rules(id),
    severity      TEXT NOT NULL CHECK (severity IN ('low','med','high')),
    detected_at   TEXT NOT NULL DEFAULT (datetime('now')),
    evidence_json TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('open','reviewed','dismissed')) DEFAULT 'open'
);

CREATE TABLE IF NOT EXISTS judge_audits (
    id           TEXT PRIMARY KEY,
    scope        TEXT NOT NULL,
    target_id    TEXT,
    started_at   TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at  TEXT,
    findings_md  TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_witness_service_action ON judge_witness_log(service, action);
CREATE INDEX IF NOT EXISTS idx_peer_scorer_target    ON netdef_peer_scores(scorer_id, target_task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_assignee        ON team_tasks(assignee_id);
CREATE INDEX IF NOT EXISTS idx_ballots_vote          ON money_ballots(vote_id);

"""Initialize scoring.db with schema + seed data.

Usage:
    python -m shared.bootstrap            # create if missing (demo seed only)
    python -m shared.bootstrap --reset    # drop and recreate
    python -m shared.bootstrap --iveel    # also seed the Iveel × Dealy plan
"""
import argparse
import json
from pathlib import Path

from shared.db import DB_PATH, connect, new_id
from shared.constants import (
    CONTAINER_TARGET, CONTAINER_START, CONTAINER_END, CONTAINER_AGENT_HANDLE,
    MEMBERS, MILESTONES, TASK_ASSIGNMENTS, PROJECTS,
)

SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
CONTAINER_SCHEMA_FILE = Path(__file__).resolve().parent / "container_schema.sql"


SEED_RULES = [
    ("peer_score_collusion", "collusion",
     {"mean_threshold": 90, "share_threshold": 0.6, "min_pair_volume": 3}),
    ("money_vote_rigging", "vote_rigging",
     {"clique_min_size": 3, "consecutive_wins": 3, "close_window_seconds": 300}),
    ("kpi_gaming", "kpi_gaming",
     {"stddev_multiplier": 3.0, "self_assign_weight_ratio": 1.5}),
]

# Demo seed — kept for backwards compatibility with existing tests.
SEED_WORKERS = [
    ("Ada Lovelace", "human", "ada", 120000),
    ("Grace Hopper", "human", "grace", 130000),
    ("Alan Turing",  "human", "alan", 140000),
    ("Agent-Smith",  "agent", "smith", 0),
    ("Agent-Echo",   "agent", "echo", 0),
]


def reset() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = DB_PATH.with_name(DB_PATH.name + suffix)
        if sidecar.exists():
            sidecar.unlink()


def seed_iveel(conn) -> None:
    """Seed the Iveel × Dealy frozen plan: members, projects, tasks, milestones,
    container row. Idempotent: skips anything that already exists by name/handle.
    Call this AFTER init() if you want the Iveel data on top of the empty DB.
    """

    # 1) Members (humans + 1 agent monitor)
    handle_to_id: dict[str, str] = {}
    for m in MEMBERS:
        existing = conn.execute(
            "SELECT id FROM team_workers WHERE handle=?", (m["handle"],)
        ).fetchone()
        if existing:
            handle_to_id[m["handle"]] = existing["id"]
            continue
        wid = new_id()
        wtype = "agent" if m.get("is_agent") else "human"
        conn.execute(
            """INSERT INTO team_workers (id, name, type, handle, base_salary, salary_currency)
               VALUES (?, ?, ?, ?, ?, 'MNT')""",
            (wid, m["name"], wtype, m["handle"], m["base_salary"]),
        )
        handle_to_id[m["handle"]] = wid

    # 2) Projects (the 7 sheet projects mirror team service)
    proj_to_id: dict[str, str] = {}
    for name in PROJECTS:
        existing = conn.execute(
            "SELECT id FROM team_projects WHERE name=?", (name,)
        ).fetchone()
        if existing:
            proj_to_id[name] = existing["id"]
            continue
        pid = new_id()
        conn.execute(
            "INSERT INTO team_projects (id, name) VALUES (?, ?)", (pid, name)
        )
        proj_to_id[name] = pid

    # 3) Tasks per (project, member). Idempotent.
    for ta in TASK_ASSIGNMENTS:
        pid = proj_to_id.get(ta["project"])
        wid = handle_to_id.get(ta["member"])
        if not pid or not wid:
            continue
        existing = conn.execute(
            """SELECT id FROM team_tasks
               WHERE project_id=? AND assignee_id=? AND title=?""",
            (pid, wid, ta["title"]),
        ).fetchone()
        if existing:
            continue
        tid = new_id()
        conn.execute(
            """INSERT INTO team_tasks
               (id, project_id, title, weight, assignee_id, status)
               VALUES (?, ?, ?, ?, ?, 'open')""",
            (tid, pid, ta["title"], ta["weight"], wid),
        )

    # 4) Container row (one, frozen).
    existing_container = conn.execute(
        "SELECT id FROM container_state LIMIT 1"
    ).fetchone()
    if not existing_container:
        monitor_id = handle_to_id.get(CONTAINER_AGENT_HANDLE)
        conn.execute(
            """INSERT INTO container_state
               (id, target_mnt, started_at, ends_at, monitor_id)
               VALUES (?, ?, ?, ?, ?)""",
            (new_id(), CONTAINER_TARGET, CONTAINER_START, CONTAINER_END, monitor_id),
        )

    # 5) Milestone progress rows (one per const milestone, 'pending').
    for ms in MILESTONES:
        existing = conn.execute(
            "SELECT milestone_id FROM container_milestone_progress WHERE milestone_id=?",
            (ms["id"],),
        ).fetchone()
        if existing:
            continue
        conn.execute(
            """INSERT INTO container_milestone_progress
               (milestone_id, status, completion_pct) VALUES (?, 'pending', 0)""",
            (ms["id"],),
        )


def init(seed: bool = True, iveel: bool = False) -> None:
    schema = SCHEMA_FILE.read_text()
    container_schema = CONTAINER_SCHEMA_FILE.read_text()
    conn = connect()
    try:
        conn.executescript(schema)
        conn.executescript(container_schema)
        if seed:
            existing = conn.execute("SELECT COUNT(*) AS c FROM judge_anomaly_rules").fetchone()["c"]
            if existing == 0:
                for name, rule_type, params in SEED_RULES:
                    conn.execute(
                        "INSERT INTO judge_anomaly_rules (id, name, rule_type, params_json) VALUES (?, ?, ?, ?)",
                        (new_id(), name, rule_type, json.dumps(params)),
                    )
            # Demo seed (5 generic workers) — kept for tests + first-run demos.
            existing_w = conn.execute("SELECT COUNT(*) AS c FROM team_workers").fetchone()["c"]
            if existing_w == 0:
                for name, wtype, handle, salary in SEED_WORKERS:
                    conn.execute(
                        "INSERT INTO team_workers (id, name, type, handle, base_salary) VALUES (?, ?, ?, ?, ?)",
                        (new_id(), name, wtype, handle, salary),
                    )
        if iveel:
            seed_iveel(conn)
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--no-seed", action="store_true")
    ap.add_argument("--iveel", action="store_true",
                    help="also seed the Iveel × Dealy plan (members, milestones, container)")
    args = ap.parse_args()
    if args.reset:
        reset()
    init(seed=not args.no_seed, iveel=args.iveel)
    print(f"scoring.db ready at {DB_PATH}")
    if args.iveel:
        print("  (+ Iveel × Dealy plan seeded)")


if __name__ == "__main__":
    main()

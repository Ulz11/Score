"""Rule-based anomaly detectors for the Smart Judge.

Each detector returns a list of evidence dicts. The caller writes them to
judge_anomalies and the witness log.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict


def _params(conn: sqlite3.Connection, name: str) -> dict:
    row = conn.execute(
        "SELECT id, params_json, enabled FROM judge_anomaly_rules WHERE name=?",
        (name,),
    ).fetchone()
    if not row or not row["enabled"]:
        return {}
    p = json.loads(row["params_json"])
    p["_rule_id"] = row["id"]
    return p


def peer_score_collusion(conn: sqlite3.Connection) -> list[dict]:
    """Find scorer/assignee pairs where both consistently score each other ≥ threshold
    AND that pair dominates the scorer's volume."""
    p = _params(conn, "peer_score_collusion")
    if not p:
        return []
    mean_thr = p["mean_threshold"]
    share_thr = p["share_threshold"]
    min_vol = p["min_pair_volume"]

    rows = conn.execute(
        """SELECT ps.scorer_id, t.assignee_id AS owner_id, ps.score
           FROM netdef_peer_scores ps
           JOIN team_tasks t ON t.id = ps.target_task_id
           WHERE t.assignee_id IS NOT NULL"""
    ).fetchall()

    by_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    by_scorer_total: dict[str, int] = defaultdict(int)
    for r in rows:
        by_pair[(r["scorer_id"], r["owner_id"])].append(r["score"])
        by_scorer_total[r["scorer_id"]] += 1

    findings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for (a, b), scores_ab in by_pair.items():
        if a == b:
            continue
        if (b, a) in seen or (a, b) in seen:
            continue
        scores_ba = by_pair.get((b, a))
        if not scores_ba:
            continue
        if len(scores_ab) < min_vol or len(scores_ba) < min_vol:
            continue
        mean_ab = sum(scores_ab) / len(scores_ab)
        mean_ba = sum(scores_ba) / len(scores_ba)
        share_a = len(scores_ab) / by_scorer_total[a]
        share_b = len(scores_ba) / by_scorer_total[b]
        if mean_ab >= mean_thr and mean_ba >= mean_thr and (share_a >= share_thr or share_b >= share_thr):
            findings.append({
                "rule_id": p["_rule_id"],
                "severity": "high",
                "evidence": {
                    "pair": [a, b],
                    "mean_a_to_b": round(mean_ab, 2),
                    "mean_b_to_a": round(mean_ba, 2),
                    "volume_a_to_b": len(scores_ab),
                    "volume_b_to_a": len(scores_ba),
                    "share_a": round(share_a, 2),
                    "share_b": round(share_b, 2),
                },
            })
            seen.add((a, b))
    return findings


def money_vote_rigging(conn: sqlite3.Connection) -> list[dict]:
    """Flag (a) cliques of voters who win N consecutive votes with identical 'yes' patterns,
    and (b) votes that close within close_window_seconds of reaching exact quorum."""
    p = _params(conn, "money_vote_rigging")
    if not p:
        return []
    clique_min = p["clique_min_size"]
    consec = p["consecutive_wins"]
    win_sec = p["close_window_seconds"]

    findings: list[dict] = []

    # (a) recurring yes-clique
    closed = conn.execute(
        """SELECT id FROM money_votes WHERE status='passed' ORDER BY id ASC"""
    ).fetchall()
    yes_sets: list[frozenset[str]] = []
    vote_ids: list[str] = []
    for v in closed:
        voters = conn.execute(
            "SELECT voter_id FROM money_ballots WHERE vote_id=? AND choice='yes' ORDER BY voter_id",
            (v["id"],),
        ).fetchall()
        s = frozenset(r["voter_id"] for r in voters)
        if len(s) >= clique_min:
            yes_sets.append(s)
            vote_ids.append(v["id"])
    streak = 1
    for i in range(1, len(yes_sets)):
        if yes_sets[i] == yes_sets[i - 1]:
            streak += 1
            if streak >= consec:
                findings.append({
                    "rule_id": p["_rule_id"],
                    "severity": "high",
                    "evidence": {
                        "type": "recurring_yes_clique",
                        "voters": sorted(yes_sets[i]),
                        "vote_ids": vote_ids[i - streak + 1: i + 1],
                    },
                })
                streak = 1
        else:
            streak = 1

    # (b) just-quorum, fast close
    fast_rows = conn.execute(
        """SELECT v.id AS vote_id, v.quorum_required, v.opened_at, v.closed_at,
                  (SELECT COUNT(*) FROM money_ballots b WHERE b.vote_id=v.id) AS cast_count
           FROM money_votes v
           WHERE v.status='passed' AND v.closed_at IS NOT NULL"""
    ).fetchall()
    for r in fast_rows:
        if r["cast_count"] != r["quorum_required"]:
            continue
        delta = conn.execute(
            "SELECT (julianday(?) - julianday(?)) * 86400.0 AS sec",
            (r["closed_at"], r["opened_at"]),
        ).fetchone()["sec"]
        if delta is not None and delta <= win_sec:
            findings.append({
                "rule_id": p["_rule_id"],
                "severity": "med",
                "evidence": {
                    "type": "exact_quorum_fast_close",
                    "vote_id": r["vote_id"],
                    "seconds_open": round(delta, 1),
                    "quorum_required": r["quorum_required"],
                },
            })
    return findings


def kpi_gaming(conn: sqlite3.Connection) -> list[dict]:
    """Flag (a) >3σ jumps in a worker's KPI history and (b) self-assigned tasks with
    weight > project-median * ratio."""
    p = _params(conn, "kpi_gaming")
    if not p:
        return []
    z = p["stddev_multiplier"]
    weight_ratio = p["self_assign_weight_ratio"]
    findings: list[dict] = []

    # (a) KPI value spikes
    rows = conn.execute(
        """SELECT scope_id, period, metric, value, id
           FROM team_kpis
           WHERE scope='worker'
           ORDER BY scope_id, metric, period, id"""
    ).fetchall()
    by_worker_metric: dict[tuple[str, str], list[tuple[str, float, str]]] = defaultdict(list)
    for r in rows:
        by_worker_metric[(r["scope_id"], r["metric"])].append((r["id"], r["value"], r["period"]))
    for (wid, metric), series in by_worker_metric.items():
        if len(series) < 3:
            continue
        vals = [v for _, v, _ in series[:-1]]
        latest_id, latest_v, latest_period = series[-1]
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        sd = math.sqrt(var)
        if sd > 0 and (latest_v - mean) > z * sd:
            findings.append({
                "rule_id": p["_rule_id"],
                "severity": "med",
                "evidence": {
                    "type": "kpi_value_spike",
                    "worker_id": wid,
                    "metric": metric,
                    "period": latest_period,
                    "latest": latest_v,
                    "history_mean": round(mean, 2),
                    "history_stddev": round(sd, 2),
                },
            })

    # (b) self-assigned heavy tasks
    proj_rows = conn.execute("SELECT id FROM team_projects").fetchall()
    for proj in proj_rows:
        weights = [r["weight"] for r in conn.execute(
            "SELECT weight FROM team_tasks WHERE project_id=?", (proj["id"],)
        ).fetchall()]
        if not weights:
            continue
        weights_sorted = sorted(weights)
        median = weights_sorted[len(weights_sorted) // 2]
        suspects = conn.execute(
            """SELECT id, title, weight, assignee_id, created_by
               FROM team_tasks
               WHERE project_id=? AND assignee_id IS NOT NULL
                 AND created_by = assignee_id""",
            (proj["id"],),
        ).fetchall()
        for s in suspects:
            if median > 0 and s["weight"] > median * weight_ratio:
                findings.append({
                    "rule_id": p["_rule_id"],
                    "severity": "low",
                    "evidence": {
                        "type": "self_assigned_heavy_task",
                        "task_id": s["id"],
                        "worker_id": s["assignee_id"],
                        "weight": s["weight"],
                        "project_median_weight": median,
                    },
                })
    return findings


ALL_DETECTORS = {
    "peer_score_collusion": peer_score_collusion,
    "money_vote_rigging": money_vote_rigging,
    "kpi_gaming": kpi_gaming,
}

from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from shared.db import new_id

GENESIS_HASH = "0" * 64


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash(prev_hash: str, payload_canonical: str) -> str:
    return hashlib.sha256((prev_hash + payload_canonical).encode("utf-8")).hexdigest()


def append(
    conn: sqlite3.Connection,
    *,
    actor_id: str | None,
    service: str,
    action: str,
    target_type: str,
    target_id: str | None,
    payload: dict[str, Any],
) -> str:
    """Append a row to the hash-chained witness log. Returns the new row's UUID7."""
    row = conn.execute(
        "SELECT payload_hash FROM judge_witness_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = row["payload_hash"] if row else GENESIS_HASH
    payload_canonical = _canonical(payload)
    payload_hash = _hash(prev_hash, payload_canonical)
    wid = new_id()
    conn.execute(
        """
        INSERT INTO judge_witness_log
          (id, actor_id, service, action, target_type, target_id,
           payload_json, payload_hash, prev_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (wid, actor_id, service, action, target_type, target_id,
         payload_canonical, payload_hash, prev_hash),
    )
    return wid


def verify_chain(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT id, payload_json, payload_hash, prev_hash FROM judge_witness_log ORDER BY id ASC"
    ).fetchall()
    expected_prev = GENESIS_HASH
    for r in rows:
        recomputed = _hash(expected_prev, r["payload_json"])
        if r["prev_hash"] != expected_prev or r["payload_hash"] != recomputed:
            return {"ok": False, "broken_at_id": r["id"], "rows_checked": len(rows)}
        expected_prev = r["payload_hash"]
    return {"ok": True, "rows_checked": len(rows)}

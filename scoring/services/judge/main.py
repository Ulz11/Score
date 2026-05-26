"""Smart Judge service: witness log, chain verification, anomaly detection, audits.
All ids are UUID7 strings; witness cursor is a UUID7 string (UUID7 lex-sorts by time)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from shared import witness
from shared.db import new_id, transaction
from shared.deps import require_admin
from shared.models import AuditIn
from services.judge.detectors import ALL_DETECTORS

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://127.0.0.1:8010")

app = FastAPI(title="scoring-judge", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
SERVICE = "judge"


@app.get("/healthz")
def healthz() -> dict:
    return {"service": SERVICE, "ok": True}


@app.get("/witness")
def list_witness(since: str | None = None, limit: int = 200) -> list[dict]:
    """List witness rows after the given UUID7 cursor (exclusive).
    Omit `since` (or send empty) to fetch from the beginning."""
    with transaction() as conn:
        if since:
            rows = conn.execute(
                "SELECT * FROM judge_witness_log WHERE id > ? ORDER BY id ASC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM judge_witness_log ORDER BY id ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/witness/verify")
def verify_witness() -> dict:
    with transaction() as conn:
        return witness.verify_chain(conn)


@app.post("/detectors/run")
def run_detectors(only: str | None = None, admin: dict = Depends(require_admin)) -> dict:
    """Run all (or one) anomaly detector and persist results."""
    results: dict[str, list[dict]] = {}
    with transaction() as conn:
        targets = ALL_DETECTORS if only is None else {only: ALL_DETECTORS[only]} if only in ALL_DETECTORS else {}
        if only is not None and only not in ALL_DETECTORS:
            raise HTTPException(404, f"unknown detector: {only}")
        for name, fn in targets.items():
            findings = fn(conn)
            results[name] = findings
            for f in findings:
                aid = new_id()
                conn.execute(
                    """INSERT INTO judge_anomalies (id, rule_id, severity, evidence_json)
                       VALUES (?, ?, ?, ?)""",
                    (aid, f["rule_id"], f["severity"], json.dumps(f["evidence"])),
                )
                witness.append(
                    conn,
                    actor_id=None,
                    service=SERVICE,
                    action="anomaly.detected",
                    target_type="anomaly",
                    target_id=aid,
                    payload={"rule_id": f["rule_id"], "severity": f["severity"],
                             "evidence": f["evidence"]},
                )
    return {"results": {k: len(v) for k, v in results.items()}, "details": results}


@app.get("/anomalies")
def list_anomalies(status: str | None = None) -> list[dict]:
    with transaction() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM judge_anomalies WHERE status=? ORDER BY id DESC", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM judge_anomalies ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.post("/audits", status_code=201)
def open_audit(body: AuditIn, admin: dict = Depends(require_admin)) -> dict:
    """Open an audit and immediately produce findings markdown summarizing
    anomalies that overlap with the scope (best-effort)."""
    with transaction() as conn:
        aid = new_id()
        conn.execute(
            "INSERT INTO judge_audits (id, scope, target_id) VALUES (?, ?, ?)",
            (aid, body.scope, body.target_id),
        )
        anomalies = conn.execute(
            "SELECT a.*, r.name AS rule_name FROM judge_anomalies a JOIN judge_anomaly_rules r ON r.id=a.rule_id"
        ).fetchall()
        lines = [f"# Audit {aid} ({body.scope}, target={body.target_id})",
                 f"_generated {datetime.now(timezone.utc).isoformat()}_", ""]
        if not anomalies:
            lines.append("No anomalies on record.")
        else:
            lines.append(f"## {len(anomalies)} anomalies on record")
            for a in anomalies:
                lines.append(f"- **{a['rule_name']}** (sev={a['severity']}, status={a['status']}): "
                             f"{a['evidence_json']}")
        chain = witness.verify_chain(conn)
        lines += ["", "## Witness chain",
                  f"- ok: **{chain['ok']}**",
                  f"- rows checked: {chain['rows_checked']}"]
        if not chain["ok"]:
            lines.append(f"- BROKEN AT id={chain.get('broken_at_id')}")
        findings_md = "\n".join(lines)
        finished_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE judge_audits SET findings_md=?, finished_at=? WHERE id=?",
            (findings_md, finished_at, aid),
        )
        witness.append(
            conn,
            actor_id=body.actor_id,
            service=SERVICE,
            action="audit.completed",
            target_type="audit",
            target_id=aid,
            payload={"scope": body.scope, "target_id": body.target_id,
                     "anomalies_count": len(anomalies), "chain_ok": chain["ok"]},
        )
        row = conn.execute("SELECT * FROM judge_audits WHERE id=?", (aid,)).fetchone()
        return dict(row)

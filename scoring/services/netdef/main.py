"""Network defense service: peer scores (including unfinished tasks),
comments, @mentions. All ids are UUID7 strings."""
from __future__ import annotations

import os
import re
import sqlite3

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from shared import witness
from shared.db import new_id, transaction
from shared.deps import assert_can_act_as, current_session
from shared.models import CommentIn, PeerScoreIn

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://127.0.0.1:8010")

app = FastAPI(title="scoring-netdef", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
SERVICE = "netdef"


@app.get("/healthz")
def healthz() -> dict:
    return {"service": SERVICE, "ok": True}

MENTION_RE = re.compile(r"@([a-zA-Z0-9_\-]+)")


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r else None


@app.post("/peer-scores", status_code=201)
def add_peer_score(body: PeerScoreIn, request: Request) -> dict:
    with transaction() as conn:
        # If the named scorer has a password, the request must be authenticated
        # as them (or as admin). Otherwise allow (legacy 'Acting as' flow).
        assert_can_act_as(conn, request, body.scorer_id)
        task = conn.execute(
            "SELECT id, assignee_id, status FROM team_tasks WHERE id=?",
            (body.target_task_id,),
        ).fetchone()
        if not task:
            raise HTTPException(404, "task not found")
        scorer = conn.execute(
            "SELECT id FROM team_workers WHERE id=?", (body.scorer_id,)
        ).fetchone()
        if not scorer:
            raise HTTPException(404, "scorer not found")
        if task["assignee_id"] == body.scorer_id:
            raise HTTPException(400, "self-scoring not allowed")
        was_unfinished = task["status"] in ("open", "in_progress")
        psid = new_id()
        conn.execute(
            """INSERT INTO netdef_peer_scores
               (id, scorer_id, target_task_id, score, notes, was_unfinished)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (psid, body.scorer_id, body.target_task_id, body.score, body.notes,
             1 if was_unfinished else 0),
        )
        witness.append(
            conn,
            actor_id=body.scorer_id,
            service=SERVICE,
            action="peer_score.added",
            target_type="task",
            target_id=body.target_task_id,
            payload={"score": body.score, "scorer_id": body.scorer_id,
                     "was_unfinished": was_unfinished, "notes": body.notes},
        )
        return _row(conn.execute("SELECT * FROM netdef_peer_scores WHERE id=?", (psid,)).fetchone())


@app.post("/comments", status_code=201)
def add_comment(body: CommentIn, request: Request) -> dict:
    with transaction() as conn:
        assert_can_act_as(conn, request, body.author_id)
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (body.author_id,)).fetchone():
            raise HTTPException(404, "author not found")
        cid = new_id()
        conn.execute(
            """INSERT INTO netdef_comments (id, author_id, target_type, target_id, body)
               VALUES (?, ?, ?, ?, ?)""",
            (cid, body.author_id, body.target_type, body.target_id, body.body),
        )

        handles = set(MENTION_RE.findall(body.body))
        mention_ids: list[str] = []
        for h in handles:
            r = conn.execute("SELECT id FROM team_workers WHERE handle=?", (h,)).fetchone()
            if r:
                mid = new_id()
                conn.execute(
                    "INSERT INTO netdef_mentions (id, comment_id, mentioned_worker_id) VALUES (?, ?, ?)",
                    (mid, cid, r["id"]),
                )
                mention_ids.append(r["id"])

        witness.append(
            conn,
            actor_id=body.author_id,
            service=SERVICE,
            action="comment.added",
            target_type=body.target_type,
            target_id=body.target_id,
            payload={"author_id": body.author_id, "comment_id": cid,
                     "mentions": mention_ids, "body": body.body},
        )
        return {
            **dict(conn.execute("SELECT * FROM netdef_comments WHERE id=?", (cid,)).fetchone()),
            "mentions": mention_ids,
        }


@app.get("/workers/{worker_id}/inbox")
def inbox(worker_id: str) -> dict:
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (worker_id,)).fetchone():
            raise HTTPException(404, "worker not found")
        mentions = conn.execute(
            """SELECT c.id AS comment_id, c.author_id, c.target_type, c.target_id,
                      c.body, c.created_at
               FROM netdef_mentions m
               JOIN netdef_comments c ON c.id = m.comment_id
               WHERE m.mentioned_worker_id=?
               ORDER BY c.id DESC""",
            (worker_id,),
        ).fetchall()
        return {"worker_id": worker_id, "mentions": [dict(r) for r in mentions]}


@app.get("/tasks/{task_id}/peer-scores")
def task_peer_scores(task_id: str) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM netdef_peer_scores WHERE target_task_id=? ORDER BY id",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/comments")
def list_comments(target_type: str, target_id: str) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            """SELECT c.*, w.name AS author_name, w.handle AS author_handle
               FROM netdef_comments c
               LEFT JOIN team_workers w ON w.id = c.author_id
               WHERE c.target_type=? AND c.target_id=?
               ORDER BY c.id DESC""",
            (target_type, target_id),
        ).fetchall()
        return [dict(r) for r in rows]

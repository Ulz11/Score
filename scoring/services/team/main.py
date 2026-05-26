"""Team service: workers, skills, projects, tasks, KPIs, performance, auth.
All ids are UUID7 strings."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from shared import auth, witness
from shared.auth import SESSION_COOKIE
from shared.db import new_id, transaction
from shared.deps import (
    assert_can_act_as, current_session, require_admin, require_session,
)
from shared.models import (
    KpiIn, ProjectIn, SkillIn, TaskIn, TaskStatusIn, WorkerIn,
)

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://127.0.0.1:8010")

SHEET_PROJECTS = [
    "Marketing campaign",
    "Social media",
    "Sells / amount",
    "IT / performance",
    "KPI rate",
    "Salary",
    "Rate / weight",
]


class SheetBootstrapIn(BaseModel):
    members: list[str]
    actor_id: str | None = None


class LoginIn(BaseModel):
    handle: str
    password: str


class PasswordIn(BaseModel):
    password: str


app = FastAPI(title="scoring-team", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
SERVICE = "team"


@app.get("/healthz")
def healthz() -> dict:
    return {"service": SERVICE, "ok": True}


# ──────────────────────────── auth ────────────────────────────

@app.post("/auth/login")
def login(body: LoginIn, request: Request, response: Response) -> dict:
    with transaction() as conn:
        row = conn.execute(
            "SELECT id, name, handle, is_admin, password_hash FROM team_workers WHERE handle=?",
            (body.handle,),
        ).fetchone()
        if not row or not auth.verify_password(body.password, row["password_hash"]):
            # Constant-ish branch to avoid trivial timing oracles.
            raise HTTPException(401, "invalid handle or password")
        ua = request.headers.get("user-agent", "")[:200]
        token, expires_at = auth.create_session(conn, worker_id=row["id"], user_agent=ua)
        witness.append(
            conn,
            actor_id=row["id"],
            service=SERVICE,
            action="auth.login",
            target_type="worker",
            target_id=row["id"],
            payload={"handle": body.handle},
        )
    response.set_cookie(
        SESSION_COOKIE, token,
        httponly=True, samesite="lax", path="/",
        max_age=auth.SESSION_TTL_DAYS * 86400,
    )
    return {
        "worker_id": row["id"], "name": row["name"], "handle": row["handle"],
        "is_admin": bool(row["is_admin"]), "expires_at": expires_at,
    }


@app.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    token = request.cookies.get(SESSION_COOKIE)
    with transaction() as conn:
        auth.delete_session(conn, token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/auth/whoami")
def whoami(request: Request) -> dict:
    sess = current_session(request)
    if not sess:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "worker_id": sess["worker_id"],
        "name": sess["name"],
        "handle": sess["handle"],
        "is_admin": bool(sess["is_admin"]),
    }


@app.post("/workers/{worker_id}/password")
def set_password(worker_id: str, body: PasswordIn, request: Request) -> dict:
    """Set or rotate a worker's password. Admin can set anyone's; a worker
    can set their own. Empty string clears the password (worker becomes
    act-as-able again)."""
    sess = require_session(request)
    if sess["worker_id"] != worker_id and not sess.get("is_admin"):
        raise HTTPException(403, "can only set your own password (or be admin)")
    if len(body.password) > 0 and len(body.password) < 8:
        raise HTTPException(400, "password must be at least 8 characters")
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (worker_id,)).fetchone():
            raise HTTPException(404, "worker not found")
        h = auth.hash_password(body.password) if body.password else None
        conn.execute("UPDATE team_workers SET password_hash=? WHERE id=?", (h, worker_id))
        # Invalidate all existing sessions for this worker on rotation.
        conn.execute("DELETE FROM team_sessions WHERE worker_id=?", (worker_id,))
        witness.append(
            conn,
            actor_id=sess["worker_id"],
            service=SERVICE,
            action="auth.password_set" if h else "auth.password_cleared",
            target_type="worker",
            target_id=worker_id,
            payload={"by": sess["worker_id"]},
        )
    return {"ok": True, "worker_id": worker_id, "has_password": bool(h)}


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r else None


@app.post("/workers", status_code=201)
def create_worker(body: WorkerIn, admin: dict = Depends(require_admin)) -> dict:
    with transaction() as conn:
        wid = new_id()
        try:
            conn.execute(
                """INSERT INTO team_workers (id, name, type, handle, base_salary, salary_currency)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (wid, body.name, body.type, body.handle, body.base_salary, body.salary_currency),
            )
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f"worker conflict: {e}")
        witness.append(
            conn,
            actor_id=admin["worker_id"],
            service=SERVICE,
            action="worker.created",
            target_type="worker",
            target_id=wid,
            payload={"name": body.name, "type": body.type, "handle": body.handle,
                     "base_salary": body.base_salary, "salary_currency": body.salary_currency},
        )
        return _row(conn.execute("SELECT * FROM team_workers WHERE id=?", (wid,)).fetchone())


@app.get("/workers")
def list_workers() -> list[dict]:
    with transaction() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM team_workers ORDER BY id").fetchall()]


@app.post("/workers/{worker_id}/skills", status_code=201)
def add_skill(worker_id: str, body: SkillIn) -> dict:
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (worker_id,)).fetchone():
            raise HTTPException(404, "worker not found")
        sid = new_id()
        conn.execute(
            "INSERT INTO team_skills (id, worker_id, skill_name, level, notes) VALUES (?, ?, ?, ?, ?)",
            (sid, worker_id, body.skill_name, body.level, body.notes),
        )
        witness.append(
            conn,
            actor_id=body.actor_id or worker_id,
            service=SERVICE,
            action="skill.added",
            target_type="worker",
            target_id=worker_id,
            payload={"skill_name": body.skill_name, "level": body.level, "notes": body.notes},
        )
        return _row(conn.execute("SELECT * FROM team_skills WHERE id=?", (sid,)).fetchone())


@app.get("/projects")
def list_projects() -> list[dict]:
    with transaction() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM team_projects ORDER BY id").fetchall()]


@app.get("/projects/{project_id}/tasks")
def list_project_tasks(project_id: str) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM team_tasks WHERE project_id=? ORDER BY id",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM team_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "task not found")
        return dict(row)


@app.post("/sheet/bootstrap")
def sheet_bootstrap(body: SheetBootstrapIn, admin: dict = Depends(require_admin)) -> dict:
    """Idempotently ensure the 7 sheet projects and one task per (project, member)
    exist. Resolves member names by `name` first, then `handle`; creates a worker
    if neither matches. Returns the (project, member) -> task_id mapping."""
    members = body.members
    with transaction() as conn:
        # 1) resolve / create members
        member_ids: list[str] = []
        for name in members:
            r = conn.execute(
                "SELECT id FROM team_workers WHERE name=? OR handle=?",
                (name, name.lower()),
            ).fetchone()
            if r:
                member_ids.append(r["id"])
                continue
            handle = name.lower().replace(" ", "_") or f"member_{len(member_ids)+1}"
            wid = new_id()
            try:
                conn.execute(
                    "INSERT INTO team_workers (id, name, type, handle) VALUES (?, ?, 'human', ?)",
                    (wid, name, handle),
                )
            except Exception:
                conn.execute(
                    "INSERT INTO team_workers (id, name, type, handle) VALUES (?, ?, 'human', ?)",
                    (wid, name, f"{handle}_{len(member_ids)+1}"),
                )
            member_ids.append(wid)

        # 2) resolve / create the 7 projects (in fixed order)
        project_ids: list[str] = []
        for pname in SHEET_PROJECTS:
            r = conn.execute("SELECT id FROM team_projects WHERE name=?", (pname,)).fetchone()
            if r:
                project_ids.append(r["id"])
            else:
                pid = new_id()
                conn.execute(
                    "INSERT INTO team_projects (id, name) VALUES (?, ?)", (pid, pname)
                )
                project_ids.append(pid)

        # 3) ensure each (project, member) has a task
        tasks: dict[str, dict[str, str]] = {}
        for pname, pid in zip(SHEET_PROJECTS, project_ids):
            tasks[pid] = {}
            existing = conn.execute(
                """SELECT id, assignee_id FROM team_tasks
                   WHERE project_id=? AND assignee_id IS NOT NULL""",
                (pid,),
            ).fetchall()
            by_member = {r["assignee_id"]: r["id"] for r in existing}
            for name, mid in zip(members, member_ids):
                if mid in by_member:
                    tasks[pid][mid] = by_member[mid]
                else:
                    tid = new_id()
                    conn.execute(
                        """INSERT INTO team_tasks (id, project_id, title, weight, assignee_id, created_by)
                           VALUES (?, ?, ?, 5, ?, ?)""",
                        (tid, pid, f"{pname} — {name}", mid, body.actor_id),
                    )
                    tasks[pid][mid] = tid

        witness.append(
            conn,
            actor_id=body.actor_id,
            service=SERVICE,
            action="sheet.bootstrapped",
            target_type="sheet",
            target_id=None,
            payload={"members": list(zip(members, member_ids)),
                     "projects": list(zip(SHEET_PROJECTS, project_ids))},
        )

        return {
            "members": [{"name": n, "id": i} for n, i in zip(members, member_ids)],
            "projects": [{"name": n, "id": i} for n, i in zip(SHEET_PROJECTS, project_ids)],
            "tasks": tasks,
        }


@app.post("/projects", status_code=201)
def create_project(body: ProjectIn, admin: dict = Depends(require_admin)) -> dict:
    with transaction() as conn:
        pid = new_id()
        try:
            conn.execute(
                "INSERT INTO team_projects (id, name, description) VALUES (?, ?, ?)",
                (pid, body.name, body.description),
            )
        except sqlite3.IntegrityError as e:
            raise HTTPException(409, f"project conflict: {e}")
        witness.append(
            conn,
            actor_id=body.actor_id,
            service=SERVICE,
            action="project.created",
            target_type="project",
            target_id=pid,
            payload={"name": body.name, "description": body.description},
        )
        return _row(conn.execute("SELECT * FROM team_projects WHERE id=?", (pid,)).fetchone())


@app.post("/projects/{project_id}/tasks", status_code=201)
def create_task(project_id: str, body: TaskIn, admin: dict = Depends(require_admin)) -> dict:
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM team_projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(404, "project not found")
        tid = new_id()
        conn.execute(
            """INSERT INTO team_tasks
               (id, project_id, title, description, weight, assignee_id, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tid, project_id, body.title, body.description, body.weight,
             body.assignee_id, body.created_by),
        )
        witness.append(
            conn,
            actor_id=body.actor_id or body.created_by,
            service=SERVICE,
            action="task.created",
            target_type="task",
            target_id=tid,
            payload={"project_id": project_id, "title": body.title, "weight": body.weight,
                     "assignee_id": body.assignee_id, "created_by": body.created_by},
        )
        return _row(conn.execute("SELECT * FROM team_tasks WHERE id=?", (tid,)).fetchone())


@app.post("/tasks/{task_id}/status")
def update_task_status(task_id: str, body: TaskStatusIn, request: Request) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM team_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "task not found")
        # Authorize: assignee themselves, admin, or anyone if the assignee is
        # password-less (legacy 'Acting as' flow).
        sess = current_session(request)
        actor_id = sess["worker_id"] if sess else body.actor_id
        assignee = row["assignee_id"]
        if assignee:
            assert_can_act_as(conn, request, assignee)
        completed_at = datetime.now(timezone.utc).isoformat() if body.status == "done" else None
        conn.execute(
            "UPDATE team_tasks SET status=?, completed_at=? WHERE id=?",
            (body.status, completed_at, task_id),
        )
        witness.append(
            conn,
            actor_id=actor_id,
            service=SERVICE,
            action="task.status_changed",
            target_type="task",
            target_id=task_id,
            payload={"from": row["status"], "to": body.status},
        )
        # Notify the assignee when someone else changes their task status
        if assignee and actor_id and actor_id != assignee:
            from_row = conn.execute(
                "SELECT name FROM team_workers WHERE id=?", (actor_id,)
            ).fetchone()
            from_name = from_row["name"] if from_row else "Someone"
            notif_body = (
                f"{from_name} changed your task "
                f"'{row['title']}' to {body.status.replace('_', ' ')}"
            )
            conn.execute(
                """INSERT INTO team_notifications (id, worker_id, kind, ref_id, body)
                   VALUES (?, ?, 'status_change', ?, ?)""",
                (new_id(), assignee, task_id, notif_body),
            )
        return _row(conn.execute("SELECT * FROM team_tasks WHERE id=?", (task_id,)).fetchone())


@app.post("/kpis", status_code=201)
def record_kpi(body: KpiIn, request: Request) -> dict:
    sess = require_session(request)
    actor_id = body.actor_id or sess["worker_id"]
    with transaction() as conn:
        ratio = (body.value / body.target) if body.target else 0.0
        score = max(0.0, min(2.0, ratio)) * 50.0
        kid = new_id()
        conn.execute(
            """INSERT INTO team_kpis (id, scope, scope_id, period, metric, value, target, score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (kid, body.scope, body.scope_id, body.period, body.metric, body.value, body.target, score),
        )
        witness.append(
            conn,
            actor_id=actor_id,
            service=SERVICE,
            action="kpi.recorded",
            target_type=body.scope,
            target_id=body.scope_id,
            payload={"period": body.period, "metric": body.metric,
                     "value": body.value, "target": body.target, "score": score},
        )
        return _row(conn.execute("SELECT * FROM team_kpis WHERE id=?", (kid,)).fetchone())


@app.get("/workers/{worker_id}/performance")
def compute_performance(worker_id: str, period: str) -> dict:
    """Compute and persist a performance score for the period.

    components = {
      weighted_tasks: sum(weight * (done? 1 : 0)) / sum(weight)  * 100,
      kpi_avg:       mean(score) over worker KPIs in period,
      peer_avg:      mean(score) of peer scores on this worker's tasks
    }
    final = 0.5 * weighted_tasks + 0.3 * kpi_avg + 0.2 * peer_avg
    """
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (worker_id,)).fetchone():
            raise HTTPException(404, "worker not found")
        tasks = conn.execute(
            "SELECT weight, status FROM team_tasks WHERE assignee_id=?",
            (worker_id,),
        ).fetchall()
        total_weight = sum(t["weight"] for t in tasks) or 0
        done_weight = sum(t["weight"] for t in tasks if t["status"] == "done")
        weighted_tasks = (done_weight / total_weight * 100.0) if total_weight else 0.0

        kpi_rows = conn.execute(
            "SELECT score FROM team_kpis WHERE scope='worker' AND scope_id=? AND period=?",
            (worker_id, period),
        ).fetchall()
        kpi_avg = (sum(r["score"] for r in kpi_rows) / len(kpi_rows)) if kpi_rows else 0.0

        peer_rows = conn.execute(
            """SELECT ps.score FROM netdef_peer_scores ps
               JOIN team_tasks t ON t.id = ps.target_task_id
               WHERE t.assignee_id=?""",
            (worker_id,),
        ).fetchall()
        peer_avg = (sum(r["score"] for r in peer_rows) / len(peer_rows)) if peer_rows else 0.0

        final = 0.5 * weighted_tasks + 0.3 * kpi_avg + 0.2 * peer_avg
        components = {
            "weighted_tasks": round(weighted_tasks, 2),
            "kpi_avg": round(kpi_avg, 2),
            "peer_avg": round(peer_avg, 2),
        }
        psid = new_id()
        conn.execute(
            """INSERT INTO team_performance_scores (id, worker_id, period, score, components_json)
               VALUES (?, ?, ?, ?, ?)""",
            (psid, worker_id, period, final, json.dumps(components)),
        )
        witness.append(
            conn,
            actor_id=None,
            service=SERVICE,
            action="performance.computed",
            target_type="worker",
            target_id=worker_id,
            payload={"period": period, "score": final, "components": components},
        )
        return {"worker_id": worker_id, "period": period,
                "score": round(final, 2), "components": components}


# ──────────────────────── recommendations ─────────────────────────


class RecommendIn(BaseModel):
    to_id: str
    task_id: str | None = None
    body: str


@app.post("/recommendations", status_code=201)
def create_recommendation(body: RecommendIn, admin: dict = Depends(require_admin)) -> dict:
    from_id = admin["worker_id"]
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (body.to_id,)).fetchone():
            raise HTTPException(404, "recipient not found")
        rid = new_id()
        conn.execute(
            """INSERT INTO team_recommendations (id, from_id, to_id, task_id, body)
               VALUES (?, ?, ?, ?, ?)""",
            (rid, from_id, body.to_id, body.task_id, body.body),
        )
        from_row = conn.execute(
            "SELECT name FROM team_workers WHERE id=?", (from_id,)
        ).fetchone()
        from_name = from_row["name"] if from_row else "Admin"
        notif_body = f"{from_name} recommended: {body.body[:120]}"
        conn.execute(
            """INSERT INTO team_notifications (id, worker_id, kind, ref_id, body)
               VALUES (?, ?, 'recommendation', ?, ?)""",
            (new_id(), body.to_id, rid, notif_body),
        )
        witness.append(
            conn,
            actor_id=from_id,
            service=SERVICE,
            action="recommendation.created",
            target_type="worker",
            target_id=body.to_id,
            payload={"to_id": body.to_id, "task_id": body.task_id, "body": body.body},
        )
        return _row(conn.execute(
            "SELECT * FROM team_recommendations WHERE id=?", (rid,)
        ).fetchone())


@app.get("/tasks/{task_id}/recommendations")
def get_task_recommendations(task_id: str) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            """SELECT r.*, w.name AS from_name, w2.name AS to_name
               FROM team_recommendations r
               JOIN team_workers w  ON w.id  = r.from_id
               JOIN team_workers w2 ON w2.id = r.to_id
               WHERE r.task_id=? ORDER BY r.created_at DESC""",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/workers/{worker_id}/recommendations")
def get_worker_recommendations(worker_id: str, request: Request) -> list[dict]:
    sess = current_session(request)
    if not sess:
        raise HTTPException(401, "sign in required")
    if sess["worker_id"] != worker_id and not sess.get("is_admin"):
        raise HTTPException(403, "forbidden")
    with transaction() as conn:
        rows = conn.execute(
            """SELECT r.*, w.name AS from_name FROM team_recommendations r
               JOIN team_workers w ON w.id = r.from_id
               WHERE r.to_id=? ORDER BY r.created_at DESC""",
            (worker_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# ──────────────────────── notifications ───────────────────────────


@app.get("/workers/{worker_id}/notifications")
def get_notifications(worker_id: str, request: Request) -> list[dict]:
    sess = current_session(request)
    if not sess:
        raise HTTPException(401, "sign in required")
    if sess["worker_id"] != worker_id and not sess.get("is_admin"):
        raise HTTPException(403, "forbidden")
    with transaction() as conn:
        rows = conn.execute(
            """SELECT * FROM team_notifications WHERE worker_id=?
               ORDER BY created_at DESC LIMIT 50""",
            (worker_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/workers/{worker_id}/notifications/read-all")
def mark_notifications_read(worker_id: str, request: Request) -> dict:
    sess = current_session(request)
    if not sess:
        raise HTTPException(401, "sign in required")
    if sess["worker_id"] != worker_id and not sess.get("is_admin"):
        raise HTTPException(403, "forbidden")
    with transaction() as conn:
        conn.execute(
            "UPDATE team_notifications SET is_read=1 WHERE worker_id=?",
            (worker_id,),
        )
        return {"ok": True}


# ─────────────────────── task status history ──────────────────────


@app.get("/tasks/{task_id}/history")
def get_task_history(task_id: str) -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            """SELECT ts, actor_id, action, payload_json
               FROM judge_witness_log
               WHERE target_id=? AND action='task.status_changed'
               ORDER BY ts DESC LIMIT 50""",
            (task_id,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d.pop("payload_json"))
            except Exception:
                d["payload"] = {}
            actor = (
                conn.execute(
                    "SELECT name, handle FROM team_workers WHERE id=?", (d["actor_id"],)
                ).fetchone()
                if d.get("actor_id") else None
            )
            d["actor_name"] = actor["name"] if actor else "system"
            result.append(d)
        return result

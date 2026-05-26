"""Shared FastAPI deps for cross-service auth. Each service imports these.

Auth model (hybrid: "Admin + opt-in passwords"):
  - If a worker has password_hash set, they MUST log in to be the actor on any
    mutation that names them. Their /comments and /peer-scores must come from
    their session.
  - Workers without password_hash can be acted-as freely (the existing
    'Acting as' picker still works for them).
  - Admin-gated endpoints (worker create, project create, sheet bootstrap,
    kpi record, detectors run, vote close, audit open) always require an
    authenticated admin session.
"""
from __future__ import annotations

from fastapi import Cookie, HTTPException, Request

from shared.auth import SESSION_COOKIE, get_session
from shared.db import transaction


def current_session(request: Request) -> dict | None:
    """Read sid from cookie, return a session dict or None. Cheap: 1 indexed
    SQLite SELECT. Never raises."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with transaction() as conn:
        return get_session(conn, token)


def require_session(request: Request) -> dict:
    """Block unauthenticated callers. Returns the session dict."""
    sess = current_session(request)
    if not sess:
        raise HTTPException(401, "authentication required")
    return sess


def require_admin(request: Request) -> dict:
    """Block non-admins. Returns the session dict."""
    sess = require_session(request)
    if not sess.get("is_admin"):
        raise HTTPException(403, "admin only")
    return sess


def worker_is_password_protected(conn, worker_id: str) -> bool:
    r = conn.execute(
        "SELECT password_hash FROM team_workers WHERE id=?", (worker_id,)
    ).fetchone()
    if not r:
        return False
    return bool(r["password_hash"])


def assert_can_act_as(conn, request: Request, actor_id: str | None) -> None:
    """Reject a write whose declared actor (author_id/scorer_id/voter_id…) is a
    password-protected worker, unless the request is authenticated as that
    worker or as an admin. Password-less workers (no password_hash) remain
    freely act-as-able to preserve the Acting-as picker UX."""
    if not actor_id:
        return
    if not worker_is_password_protected(conn, actor_id):
        return
    sess = current_session(request)
    if not sess:
        raise HTTPException(401, "this worker requires login to act as")
    if sess["worker_id"] != actor_id and not sess.get("is_admin"):
        raise HTTPException(403, "cannot act as another password-protected worker")

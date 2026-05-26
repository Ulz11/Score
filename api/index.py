"""Vercel entry point: all 5 FastAPI services combined under /api/<svc>/."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make scoring packages importable (scoring/ is a sibling of api/)
sys.path.insert(0, str(Path(__file__).parent.parent / "scoring"))

# On Vercel /tmp is the only writable path.
os.environ.setdefault("SCORING_DB", "/tmp/scoring.db")
# Allow same-origin requests (frontend is on the same Vercel domain)
os.environ.setdefault("CORS_ORIGIN", "*")

# Bootstrap DB on cold start (idempotent)
from shared.bootstrap import init as _init
_init(seed=True, iveel=True)

# Ensure Obama (project leader) exists as admin on every cold start.
# If the bootstrap already created an Obama worker, just promote it.
def _ensure_admin() -> None:
    from shared import auth
    from shared.db import new_id, transaction
    pw = os.environ.get("ADMIN_PASSWORD", "admin1234")
    with transaction() as conn:
        # Already have an Obama admin — nothing to do.
        row = conn.execute(
            "SELECT id FROM team_workers WHERE handle='obama' AND is_admin=1"
        ).fetchone()
        if row:
            return
        # Obama worker exists but not yet admin (e.g. created by bootstrap) — promote.
        existing = conn.execute(
            "SELECT id FROM team_workers WHERE name='Obama' OR handle='obama'"
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE team_workers SET is_admin=1, password_hash=?, handle='obama' WHERE id=?",
                (auth.hash_password(pw), existing["id"]),
            )
            return
        # Fresh DB — create Obama as admin.
        conn.execute(
            """INSERT INTO team_workers (id, name, type, handle, password_hash, is_admin)
               VALUES (?, 'Obama', 'human', 'obama', ?, 1)""",
            (new_id(), auth.hash_password(pw)),
        )

_ensure_admin()

from fastapi import FastAPI
from services.team.main import app as team_app
from services.netdef.main import app as netdef_app
from services.money.main import app as money_app
from services.judge.main import app as judge_app
from services.container.main import app as container_app

app = FastAPI(title="scoring-all")

app.mount("/api/team",      team_app)
app.mount("/api/netdef",    netdef_app)
app.mount("/api/money",     money_app)
app.mount("/api/judge",     judge_app)
app.mount("/api/container", container_app)

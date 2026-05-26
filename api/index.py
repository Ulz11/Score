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

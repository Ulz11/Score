"""Per-test isolation. Each test gets:
  - its own scoring.db under tmp_path
  - a freshly seeded set of workers + anomaly rules
  - a 'testadmin' admin worker with a known password
  - 4 TestClient instances, all authenticated as that admin (session cookie set)
  - 4 'guest' TestClient instances with no session (for unauth-rejection tests)
"""
import importlib
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _reload_pkg():
    for mod in [
        "services.judge.main", "services.judge.detectors",
        "services.money.main", "services.netdef.main", "services.team.main",
        "services.container.main",
        "shared.bootstrap", "shared.witness", "shared.auth", "shared.deps",
        "shared.db", "shared.constants",
    ]:
        if mod in sys.modules:
            del sys.modules[mod]


ADMIN_HANDLE = "testadmin"
ADMIN_PW = "test-admin-pw-12345"
ADMIN_NAME = "Test Admin"


@pytest.fixture
def env(tmp_path: Path):
    db_path = tmp_path / "scoring.db"
    os.environ["SCORING_DB"] = str(db_path)
    # tests run against a localhost CORS default — that's fine for TestClient
    _reload_pkg()

    from shared.bootstrap import init
    init(seed=True)

    from shared.auth import hash_password
    from shared.db import new_id, transaction
    admin_id = new_id()
    with transaction() as conn:
        conn.execute(
            """INSERT INTO team_workers (id, name, type, handle, password_hash, is_admin)
               VALUES (?, ?, 'human', ?, ?, 1)""",
            (admin_id, ADMIN_NAME, ADMIN_HANDLE, hash_password(ADMIN_PW)),
        )

    from services.team.main      import app as team_app
    from services.netdef.main    import app as netdef_app
    from services.money.main     import app as money_app
    from services.judge.main     import app as judge_app
    from services.container.main import app as container_app

    # Log in once on the team app to get a sid; reuse on all clients.
    bootstrap_client = TestClient(team_app)
    r = bootstrap_client.post("/auth/login",
                              json={"handle": ADMIN_HANDLE, "password": ADMIN_PW})
    assert r.status_code == 200, r.text
    sid = r.cookies.get("sid")
    assert sid

    def admin_client(app):
        c = TestClient(app)
        c.cookies.set("sid", sid)
        return c

    clients = {
        "team":      admin_client(team_app),
        "netdef":    admin_client(netdef_app),
        "money":     admin_client(money_app),
        "judge":     admin_client(judge_app),
        "container": admin_client(container_app),
        "guest_team":      TestClient(team_app),
        "guest_netdef":    TestClient(netdef_app),
        "guest_money":     TestClient(money_app),
        "guest_judge":     TestClient(judge_app),
        "guest_container": TestClient(container_app),
        "admin_id":     admin_id,
        "admin_handle": ADMIN_HANDLE,
        "admin_pw":     ADMIN_PW,
        "db_path":      db_path,
    }
    yield clients
    del os.environ["SCORING_DB"]

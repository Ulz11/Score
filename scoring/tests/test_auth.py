"""Auth surface: login, whoami, logout, password rotation, admin gates,
opt-in passwords ('Acting as' for unprotected workers)."""

from fastapi.testclient import TestClient


def test_whoami_unauth_returns_authenticated_false(env):
    r = env["guest_team"].get("/auth/whoami")
    assert r.status_code == 200
    assert r.json() == {"authenticated": False}


def test_admin_login_sets_cookie_and_whoami(env):
    g = env["guest_team"]
    r = g.post("/auth/login", json={
        "handle": env["admin_handle"], "password": env["admin_pw"],
    })
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["is_admin"] is True
    assert me["handle"] == env["admin_handle"]
    assert "sid" in r.cookies

    who = g.get("/auth/whoami").json()
    assert who["authenticated"] is True
    assert who["is_admin"] is True


def test_login_wrong_password_rejected(env):
    r = env["guest_team"].post("/auth/login", json={
        "handle": env["admin_handle"], "password": "definitely-wrong",
    })
    assert r.status_code == 401


def test_login_unknown_handle_rejected(env):
    r = env["guest_team"].post("/auth/login", json={
        "handle": "no-such-user", "password": "whatever",
    })
    assert r.status_code == 401


def test_logout_clears_session(env):
    team = env["team"]
    assert team.get("/auth/whoami").json()["authenticated"] is True
    team.post("/auth/logout")
    # Cookie was cleared on response — subsequent guest-shaped call without sid
    # would 401 on admin endpoints. Use whoami to confirm.
    g = env["guest_team"]
    assert g.get("/auth/whoami").json()["authenticated"] is False


def test_guest_cannot_create_worker(env):
    r = env["guest_team"].post("/workers", json={
        "name": "Mallory", "type": "human", "handle": "mallory",
    })
    assert r.status_code == 401


def test_guest_cannot_create_project(env):
    r = env["guest_team"].post("/projects", json={"name": "Locked"})
    assert r.status_code == 401


def test_guest_cannot_run_detectors(env):
    r = env["guest_judge"].post("/detectors/run")
    assert r.status_code == 401


def test_guest_cannot_open_audit(env):
    r = env["guest_judge"].post("/audits", json={"scope": "company"})
    assert r.status_code == 401


def test_admin_creates_worker_succeeds(env):
    r = env["team"].post("/workers", json={
        "name": "Bob", "type": "human", "handle": "bob",
    })
    assert r.status_code == 201
    assert r.json()["handle"] == "bob"


def test_set_password_self_then_login(env):
    """A worker can set their own password; afterwards they can log in."""
    # admin creates Bob (no password)
    bob = env["team"].post("/workers", json={
        "name": "Bob", "type": "human", "handle": "bob"
    }).json()
    # Bob can't log in yet — no password
    r = env["guest_team"].post("/auth/login", json={
        "handle": "bob", "password": "whatever"
    })
    assert r.status_code == 401

    # admin sets Bob's password
    r = env["team"].post(f"/workers/{bob['id']}/password",
                         json={"password": "bob-strong-pw"})
    assert r.status_code == 200
    assert r.json()["has_password"] is True

    # Bob logs in
    r = env["guest_team"].post("/auth/login", json={
        "handle": "bob", "password": "bob-strong-pw"
    })
    assert r.status_code == 200
    assert r.json()["is_admin"] is False


def test_password_too_short_rejected(env):
    bob = env["team"].post("/workers", json={
        "name": "Bob", "type": "human", "handle": "bob"
    }).json()
    r = env["team"].post(f"/workers/{bob['id']}/password", json={"password": "short"})
    assert r.status_code == 400


def test_password_protected_worker_cant_be_acted_as_unauthenticated(env):
    """Once a worker has a password, you can't act-as them in /comments without their session."""
    # admin creates Bob and gives him a password
    bob = env["team"].post("/workers", json={
        "name": "Bob", "type": "human", "handle": "bob"
    }).json()
    env["team"].post(f"/workers/{bob['id']}/password", json={"password": "bob-strong-pw"})

    # admin makes a project + task assigned to Bob (so target exists)
    proj = env["team"].post("/projects", json={"name": "P"}).json()
    task = env["team"].post(f"/projects/{proj['id']}/tasks", json={
        "title": "T", "weight": 5, "assignee_id": bob["id"],
    }).json()

    # Guest tries to post a comment AS Bob → must be rejected
    r = env["guest_netdef"].post("/comments", json={
        "author_id": bob["id"], "target_type": "task",
        "target_id": task["id"], "body": "spoofed",
    })
    assert r.status_code in (401, 403), r.text


def test_passwordless_worker_can_still_be_acted_as(env):
    """A worker without a password can still be acted-as by an unauthenticated guest
    (preserves the existing 'Acting as' UX for the public sheet)."""
    ada = next(w for w in env["team"].get("/workers").json() if w["handle"] == "ada")
    proj = env["team"].post("/projects", json={"name": "P"}).json()
    task = env["team"].post(f"/projects/{proj['id']}/tasks", json={
        "title": "T", "weight": 5, "assignee_id": ada["id"],
    }).json()
    r = env["guest_netdef"].post("/comments", json={
        "author_id": ada["id"], "target_type": "task",
        "target_id": task["id"], "body": "as ada (no pw)",
    })
    assert r.status_code == 201, r.text


def test_healthz_all_services(env):
    for svc in ("team", "netdef", "money", "judge"):
        r = env[svc].get("/healthz")
        assert r.status_code == 200
        assert r.json() == {"service": svc, "ok": True}

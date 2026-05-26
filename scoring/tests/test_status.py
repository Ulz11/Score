"""Stock + Danger statuses end-to-end."""

import pytest


@pytest.mark.parametrize("new_status", ["stock", "danger", "open", "in_progress", "done", "cancelled"])
def test_status_accepts_all_six(env, new_status):
    workers = env["team"].get("/workers").json()
    ada = next(w for w in workers if w["handle"] == "ada")
    proj = env["team"].post("/projects", json={"name": f"P-{new_status}"}).json()
    task = env["team"].post(f"/projects/{proj['id']}/tasks", json={
        "title": "T", "weight": 5, "assignee_id": ada["id"],
    }).json()
    r = env["team"].post(f"/tasks/{task['id']}/status", json={"status": new_status})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == new_status


def test_status_invalid_value_rejected(env):
    workers = env["team"].get("/workers").json()
    ada = next(w for w in workers if w["handle"] == "ada")
    proj = env["team"].post("/projects", json={"name": "P-bad"}).json()
    task = env["team"].post(f"/projects/{proj['id']}/tasks", json={
        "title": "T", "weight": 5, "assignee_id": ada["id"],
    }).json()
    r = env["team"].post(f"/tasks/{task['id']}/status", json={"status": "yellow-ish"})
    assert r.status_code == 422   # pydantic literal mismatch


def test_history_persists_comment_after_status_change(env):
    """Posting a comment, then changing status, then reloading history shows both."""
    workers = env["team"].get("/workers").json()
    ada = next(w for w in workers if w["handle"] == "ada")
    proj = env["team"].post("/projects", json={"name": "P-hist"}).json()
    task = env["team"].post(f"/projects/{proj['id']}/tasks", json={
        "title": "T", "weight": 5, "assignee_id": ada["id"],
    }).json()

    env["netdef"].post("/comments", json={
        "author_id": ada["id"], "target_type": "task",
        "target_id": task["id"], "body": "starting work [link] https://x",
    })
    env["team"].post(f"/tasks/{task['id']}/status", json={"status": "stock"})

    comments = env["netdef"].get(f"/comments?target_type=task&target_id={task['id']}").json()
    assert len(comments) == 1
    assert "[link]" in comments[0]["body"]
    assert comments[0]["author_name"] == "Ada Lovelace"

    fresh = env["team"].get(f"/tasks/{task['id']}").json()
    assert fresh["status"] == "stock"

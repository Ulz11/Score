def _seed_task(env, assignee_handle: str = "ada") -> tuple[dict, dict]:
    team = env["team"]
    workers = team.get("/workers").json()
    ada = next(w for w in workers if w["handle"] == assignee_handle)
    proj = team.post("/projects", json={"name": "Apollo"}).json()
    task = team.post(f"/projects/{proj['id']}/tasks", json={
        "title": "moon plan", "weight": 4, "assignee_id": ada["id"], "created_by": ada["id"],
    }).json()
    return ada, task


def test_peer_scores_unfinished_task_allowed(env):
    netdef = env["netdef"]
    ada, task = _seed_task(env, "ada")
    grace = next(w for w in env["team"].get("/workers").json() if w["handle"] == "grace")
    r = netdef.post("/peer-scores", json={
        "scorer_id": grace["id"], "target_task_id": task["id"], "score": 75,
        "notes": "good start",
    })
    assert r.status_code == 201
    assert r.json()["was_unfinished"] == 1


def test_peer_score_rejects_self(env):
    netdef = env["netdef"]
    ada, task = _seed_task(env, "ada")
    r = netdef.post("/peer-scores", json={
        "scorer_id": ada["id"], "target_task_id": task["id"], "score": 100,
    })
    assert r.status_code == 400


def test_comment_with_mention(env):
    netdef = env["netdef"]
    workers = env["team"].get("/workers").json()
    ada = next(w for w in workers if w["handle"] == "ada")
    grace = next(w for w in workers if w["handle"] == "grace")
    r = netdef.post("/comments", json={
        "author_id": ada["id"], "target_type": "worker", "target_id": grace["id"],
        "body": "hey @grace nice work, also cc @nobody",
    })
    assert r.status_code == 201
    body = r.json()
    assert grace["id"] in body["mentions"]
    assert len(body["mentions"]) == 1

    inbox = netdef.get(f"/workers/{grace['id']}/inbox").json()
    assert len(inbox["mentions"]) == 1
    assert "@grace" in inbox["mentions"][0]["body"]

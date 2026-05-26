def test_worker_project_task_performance(env):
    team = env["team"]
    # seed has 5 workers + the testadmin from conftest
    workers = team.get("/workers").json()
    assert len(workers) == 6
    ada = next(w for w in workers if w["handle"] == "ada")

    proj = team.post("/projects", json={"name": "Mercury", "description": "first launch"}).json()
    t1 = team.post(f"/projects/{proj['id']}/tasks", json={
        "title": "design schema", "weight": 5, "assignee_id": ada["id"],
        "created_by": ada["id"],
    }).json()
    t2 = team.post(f"/projects/{proj['id']}/tasks", json={
        "title": "write API", "weight": 3, "assignee_id": ada["id"],
        "created_by": ada["id"],
    }).json()

    assert team.post(f"/tasks/{t1['id']}/status", json={"status": "done"}).status_code == 200
    # t2 stays open

    perf = team.get(f"/workers/{ada['id']}/performance", params={"period": "2026-Q2"}).json()
    # 5 done / 8 total = 62.5 ; kpi=0 ; peer=0 → 0.5*62.5 = 31.25
    assert perf["components"]["weighted_tasks"] == 62.5
    assert perf["score"] == 31.25


def test_kpi_recorded_and_scored(env):
    team = env["team"]
    workers = team.get("/workers").json()
    ada = next(w for w in workers if w["handle"] == "ada")
    k = team.post("/kpis", json={
        "scope": "worker", "scope_id": ada["id"], "period": "2026-Q2",
        "metric": "tickets_closed", "value": 80, "target": 100,
    }).json()
    # 0.8 ratio → 40
    assert k["score"] == 40.0

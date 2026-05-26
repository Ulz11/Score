import sqlite3


def test_witness_chain_ok_after_normal_writes(env):
    team = env["team"]
    team.post("/projects", json={"name": "ChainProj"})
    v = env["judge"].get("/witness/verify").json()
    assert v["ok"] is True
    assert v["rows_checked"] >= 1


def test_witness_chain_detects_tampering(env):
    team = env["team"]
    team.post("/projects", json={"name": "TamperProj"})
    # tamper with a payload directly in the DB
    conn = sqlite3.connect(env["db_path"])
    conn.execute(
        "UPDATE judge_witness_log SET payload_json=? WHERE id=("
        "SELECT id FROM judge_witness_log ORDER BY id DESC LIMIT 1)",
        ('{"tampered":true}',),
    )
    conn.commit()
    conn.close()
    v = env["judge"].get("/witness/verify").json()
    assert v["ok"] is False
    assert v["broken_at_id"] is not None


def test_collusion_detector_fires(env):
    team, netdef, judge = env["team"], env["netdef"], env["judge"]
    workers = team.get("/workers").json()
    ada = next(w for w in workers if w["handle"] == "ada")
    grace = next(w for w in workers if w["handle"] == "grace")
    proj = team.post("/projects", json={"name": "Collude"}).json()

    # Ada owns 3 tasks, Grace owns 3 tasks. They score each other 95+ each time.
    ada_tasks = [team.post(f"/projects/{proj['id']}/tasks", json={
        "title": f"a{i}", "weight": 2, "assignee_id": ada["id"]}).json() for i in range(3)]
    grace_tasks = [team.post(f"/projects/{proj['id']}/tasks", json={
        "title": f"g{i}", "weight": 2, "assignee_id": grace["id"]}).json() for i in range(3)]

    for t in ada_tasks:
        netdef.post("/peer-scores", json={"scorer_id": grace["id"],
                                          "target_task_id": t["id"], "score": 97})
    for t in grace_tasks:
        netdef.post("/peer-scores", json={"scorer_id": ada["id"],
                                          "target_task_id": t["id"], "score": 96})

    res = judge.post("/detectors/run", params={"only": "peer_score_collusion"}).json()
    assert res["results"]["peer_score_collusion"] >= 1
    anomalies = judge.get("/anomalies").json()
    assert any("pair" in a["evidence_json"] for a in anomalies)


def test_vote_rigging_exact_quorum_fast_close(env):
    money, judge = env["money"], env["judge"]
    voters = env["team"].get("/workers").json()
    meeting = money.post("/meetings", json={
        "title": "Rigged", "scheduled_at": "2026-05-20T10:00:00Z"}).json()
    vote = money.post(f"/meetings/{meeting['id']}/votes", json={
        "proposal_text": "fast yes", "quorum_required": 3, "majority_threshold": 0.5}).json()
    for v in voters[:3]:
        money.post(f"/votes/{vote['id']}/ballots", json={"voter_id": v["id"], "choice": "yes"})
    money.post(f"/votes/{vote['id']}/close")
    res = judge.post("/detectors/run", params={"only": "money_vote_rigging"}).json()
    flags = res["details"]["money_vote_rigging"]
    assert any(f["evidence"]["type"] == "exact_quorum_fast_close" for f in flags)


def test_audit_summarizes(env):
    team, judge = env["team"], env["judge"]
    team.post("/projects", json={"name": "AuditMe"})
    a = judge.post("/audits", json={"scope": "company", "target_id": None}).json()
    assert "# Audit " in a["findings_md"]
    assert "Witness chain" in a["findings_md"]

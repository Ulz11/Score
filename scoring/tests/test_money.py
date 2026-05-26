def _voters(env):
    return env["team"].get("/workers").json()


def test_binding_vote_commits_transaction(env):
    money = env["money"]
    voters = _voters(env)
    meeting = money.post("/meetings", json={
        "title": "Q2 spend", "scheduled_at": "2026-05-20T10:00:00Z",
    }).json()
    tx = money.post("/transactions", json={
        "occurred_at": "2026-05-20T10:30:00Z",
        "amount": 5000.0, "currency": "USD",
        "sender_party": "company", "receiver_party": "vendor-X",
        "location": "stripe.com", "payment_method": "card",
        "transaction_type": "transfer",
    }).json()
    assert tx["status"] == "pending_vote"

    vote = money.post(f"/meetings/{meeting['id']}/votes", json={
        "proposal_text": "Pay vendor-X $5000",
        "quorum_required": 3, "majority_threshold": 0.5,
        "linked_transaction_id": tx["id"],
    }).json()

    for v, choice in [(voters[0], "yes"), (voters[1], "yes"), (voters[2], "no")]:
        r = money.post(f"/votes/{vote['id']}/ballots",
                       json={"voter_id": v["id"], "choice": choice})
        assert r.status_code == 201

    close = money.post(f"/votes/{vote['id']}/close").json()
    assert close["status"] == "passed"
    assert close["transaction_status"] == "committed"
    tx2 = money.get(f"/transactions/{tx['id']}").json()
    assert tx2["status"] == "committed"


def test_failed_quorum_rejects_transaction(env):
    money = env["money"]
    voters = _voters(env)
    meeting = money.post("/meetings", json={
        "title": "Risky spend", "scheduled_at": "2026-05-20T11:00:00Z",
    }).json()
    tx = money.post("/transactions", json={
        "occurred_at": "2026-05-20T11:05:00Z",
        "amount": 99999.0, "currency": "USD",
        "sender_party": "company", "receiver_party": "vendor-Y",
        "payment_method": "wire", "transaction_type": "transfer",
    }).json()
    vote = money.post(f"/meetings/{meeting['id']}/votes", json={
        "proposal_text": "Pay vendor-Y",
        "quorum_required": 5, "majority_threshold": 0.5,
        "linked_transaction_id": tx["id"],
    }).json()
    money.post(f"/votes/{vote['id']}/ballots", json={"voter_id": voters[0]["id"], "choice": "yes"})
    money.post(f"/votes/{vote['id']}/ballots", json={"voter_id": voters[1]["id"], "choice": "yes"})
    close = money.post(f"/votes/{vote['id']}/close").json()
    assert close["status"] == "failed"
    assert close["transaction_status"] == "rejected"
    tx2 = money.get(f"/transactions/{tx['id']}").json()
    assert tx2["status"] == "rejected"


def test_duplicate_ballot_blocked(env):
    money = env["money"]
    voters = _voters(env)
    meeting = money.post("/meetings", json={
        "title": "dup", "scheduled_at": "2026-05-20T12:00:00Z",
    }).json()
    vote = money.post(f"/meetings/{meeting['id']}/votes", json={
        "proposal_text": "x", "quorum_required": 1,
    }).json()
    r1 = money.post(f"/votes/{vote['id']}/ballots", json={"voter_id": voters[0]["id"], "choice": "yes"})
    r2 = money.post(f"/votes/{vote['id']}/ballots", json={"voter_id": voters[0]["id"], "choice": "no"})
    assert r1.status_code == 201
    assert r2.status_code == 409

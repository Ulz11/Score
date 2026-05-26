"""Money service: meetings, binding-quorum votes, transactions, reports.
All ids are UUID7 strings."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from shared import witness
from shared.db import new_id, transaction
from shared.deps import assert_can_act_as, require_admin, require_session
from shared.models import BallotIn, MeetingIn, TransactionIn, VoteIn

CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "http://127.0.0.1:8010")

app = FastAPI(title="scoring-money", version="0.3.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[CORS_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
SERVICE = "money"


@app.get("/healthz")
def healthz() -> dict:
    return {"service": SERVICE, "ok": True}


def _row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.post("/meetings", status_code=201)
def create_meeting(body: MeetingIn, admin: dict = Depends(require_admin)) -> dict:
    with transaction() as conn:
        mid = new_id()
        conn.execute(
            "INSERT INTO money_meetings (id, title, agenda, scheduled_at, status) VALUES (?, ?, ?, ?, 'scheduled')",
            (mid, body.title, body.agenda, body.scheduled_at),
        )
        witness.append(
            conn,
            actor_id=body.actor_id,
            service=SERVICE,
            action="meeting.created",
            target_type="meeting",
            target_id=mid,
            payload={"title": body.title, "scheduled_at": body.scheduled_at},
        )
        return _row(conn.execute("SELECT * FROM money_meetings WHERE id=?", (mid,)).fetchone())


@app.post("/transactions", status_code=201)
def propose_transaction(body: TransactionIn, admin: dict = Depends(require_admin)) -> dict:
    """Always created in pending_vote with no vote yet.
    Use POST /meetings/{id}/votes with linked_transaction_id to attach a vote."""
    with transaction() as conn:
        tx_id = new_id()
        conn.execute(
            """INSERT INTO money_transactions
               (id, occurred_at, amount, currency, sender_party, receiver_party, location,
                payment_method, transaction_type, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_vote')""",
            (tx_id, body.occurred_at, body.amount, body.currency, body.sender_party,
             body.receiver_party, body.location, body.payment_method, body.transaction_type),
        )
        witness.append(
            conn,
            actor_id=body.actor_id,
            service=SERVICE,
            action="transaction.proposed",
            target_type="transaction",
            target_id=tx_id,
            payload={
                "occurred_at": body.occurred_at, "amount": body.amount, "currency": body.currency,
                "sender_party": body.sender_party, "receiver_party": body.receiver_party,
                "location": body.location, "payment_method": body.payment_method,
                "transaction_type": body.transaction_type,
            },
        )
        return _row(conn.execute("SELECT * FROM money_transactions WHERE id=?", (tx_id,)).fetchone())


@app.post("/meetings/{meeting_id}/votes", status_code=201)
def open_vote(meeting_id: str, body: VoteIn, admin: dict = Depends(require_admin)) -> dict:
    with transaction() as conn:
        if not conn.execute("SELECT 1 FROM money_meetings WHERE id=?", (meeting_id,)).fetchone():
            raise HTTPException(404, "meeting not found")
        if body.linked_transaction_id is not None:
            tx = conn.execute(
                "SELECT status FROM money_transactions WHERE id=?",
                (body.linked_transaction_id,),
            ).fetchone()
            if not tx:
                raise HTTPException(404, "linked transaction not found")
            if tx["status"] != "pending_vote":
                raise HTTPException(400, f"transaction status is {tx['status']}, not pending_vote")
        vid = new_id()
        conn.execute(
            """INSERT INTO money_votes
               (id, meeting_id, proposal_text, quorum_required, majority_threshold,
                status, linked_transaction_id)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (vid, meeting_id, body.proposal_text, body.quorum_required,
             body.majority_threshold, body.linked_transaction_id),
        )
        if body.linked_transaction_id is not None:
            conn.execute(
                "UPDATE money_transactions SET vote_id=? WHERE id=?",
                (vid, body.linked_transaction_id),
            )
        conn.execute("UPDATE money_meetings SET status='open' WHERE id=? AND status='scheduled'",
                     (meeting_id,))
        witness.append(
            conn,
            actor_id=body.actor_id,
            service=SERVICE,
            action="vote.opened",
            target_type="vote",
            target_id=vid,
            payload={"meeting_id": meeting_id, "proposal": body.proposal_text,
                     "quorum_required": body.quorum_required,
                     "majority_threshold": body.majority_threshold,
                     "linked_transaction_id": body.linked_transaction_id},
        )
        return _row(conn.execute("SELECT * FROM money_votes WHERE id=?", (vid,)).fetchone())


@app.post("/votes/{vote_id}/ballots", status_code=201)
def cast_ballot(vote_id: str, body: BallotIn, request: Request) -> dict:
    with transaction() as conn:
        # Ballot must come from the named voter (or admin) if the voter has a password.
        assert_can_act_as(conn, request, body.voter_id)
        vote = conn.execute("SELECT * FROM money_votes WHERE id=?", (vote_id,)).fetchone()
        if not vote:
            raise HTTPException(404, "vote not found")
        if vote["status"] != "open":
            raise HTTPException(400, f"vote is {vote['status']}")
        if not conn.execute("SELECT 1 FROM team_workers WHERE id=?", (body.voter_id,)).fetchone():
            raise HTTPException(404, "voter not found")
        bid = new_id()
        try:
            conn.execute(
                "INSERT INTO money_ballots (id, vote_id, voter_id, choice) VALUES (?, ?, ?, ?)",
                (bid, vote_id, body.voter_id, body.choice),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "voter already cast a ballot")
        witness.append(
            conn,
            actor_id=body.voter_id,
            service=SERVICE,
            action="ballot.cast",
            target_type="vote",
            target_id=vote_id,
            payload={"voter_id": body.voter_id, "choice": body.choice},
        )
        return _row(conn.execute("SELECT * FROM money_ballots WHERE id=?", (bid,)).fetchone())


@app.post("/votes/{vote_id}/close")
def close_vote(vote_id: str, admin: dict = Depends(require_admin)) -> dict:
    with transaction() as conn:
        vote = conn.execute("SELECT * FROM money_votes WHERE id=?", (vote_id,)).fetchone()
        if not vote:
            raise HTTPException(404, "vote not found")
        if vote["status"] != "open":
            raise HTTPException(400, f"vote is {vote['status']}")
        ballots = conn.execute(
            "SELECT choice FROM money_ballots WHERE vote_id=?", (vote_id,)
        ).fetchall()
        yes = sum(1 for b in ballots if b["choice"] == "yes")
        no = sum(1 for b in ballots if b["choice"] == "no")
        abstain = sum(1 for b in ballots if b["choice"] == "abstain")
        cast_total = yes + no + abstain
        decisive = yes + no
        quorum_ok = cast_total >= vote["quorum_required"]
        majority_ok = decisive > 0 and (yes / decisive) > vote["majority_threshold"]
        passed = quorum_ok and majority_ok
        new_status = "passed" if passed else "failed"
        closed_at = _now_iso()
        conn.execute(
            "UPDATE money_votes SET status=?, closed_at=? WHERE id=?",
            (new_status, closed_at, vote_id),
        )
        tx_status = None
        if vote["linked_transaction_id"] is not None:
            tx_status = "committed" if passed else "rejected"
            conn.execute(
                "UPDATE money_transactions SET status=? WHERE id=?",
                (tx_status, vote["linked_transaction_id"]),
            )
        witness.append(
            conn,
            actor_id=None,
            service=SERVICE,
            action="vote.closed",
            target_type="vote",
            target_id=vote_id,
            payload={"status": new_status, "yes": yes, "no": no, "abstain": abstain,
                     "quorum_required": vote["quorum_required"],
                     "linked_transaction_id": vote["linked_transaction_id"],
                     "tx_status": tx_status},
        )
        return {"vote_id": vote_id, "status": new_status,
                "tally": {"yes": yes, "no": no, "abstain": abstain},
                "linked_transaction_id": vote["linked_transaction_id"],
                "transaction_status": tx_status}


@app.get("/reports/spend")
def spend_report(period: str) -> dict:
    """Spend report for a YYYY-MM period over committed transactions."""
    with transaction() as conn:
        rows = conn.execute(
            """SELECT transaction_type, currency, COUNT(*) AS n, SUM(amount) AS total
               FROM money_transactions
               WHERE status='committed' AND substr(occurred_at, 1, 7) = ?
               GROUP BY transaction_type, currency
               ORDER BY transaction_type""",
            (period,),
        ).fetchall()
        data = [dict(r) for r in rows]
        rid = new_id()
        conn.execute(
            "INSERT INTO money_reports (id, report_type, period, data_json) VALUES (?, 'spend', ?, ?)",
            (rid, period, json.dumps(data)),
        )
        witness.append(
            conn,
            actor_id=None,
            service=SERVICE,
            action="report.generated",
            target_type="report",
            target_id=rid,
            payload={"report_type": "spend", "period": period, "rows": len(data)},
        )
        return {"period": period, "rows": data}


@app.get("/transactions/{tx_id}")
def get_transaction(tx_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM money_transactions WHERE id=?", (tx_id,)).fetchone()
        if not row:
            raise HTTPException(404, "transaction not found")
        return dict(row)


# ──────────────────── list endpoints (for the UI) ─────────────────


@app.get("/meetings")
def list_meetings() -> list[dict]:
    with transaction() as conn:
        rows = conn.execute(
            "SELECT * FROM money_meetings ORDER BY scheduled_at DESC LIMIT 100"
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM money_meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, "meeting not found")
        votes = conn.execute(
            "SELECT * FROM money_votes WHERE meeting_id=? ORDER BY opened_at DESC",
            (meeting_id,),
        ).fetchall()
        return {**dict(row), "votes": [dict(v) for v in votes]}


@app.get("/votes")
def list_votes(status: str | None = None) -> list[dict]:
    with transaction() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM money_votes WHERE status=? ORDER BY opened_at DESC LIMIT 100",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM money_votes ORDER BY opened_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/votes/{vote_id}")
def get_vote(vote_id: str) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM money_votes WHERE id=?", (vote_id,)).fetchone()
        if not row:
            raise HTTPException(404, "vote not found")
        ballots = conn.execute(
            """SELECT b.*, w.name AS voter_name, w.handle AS voter_handle
               FROM money_ballots b
               JOIN team_workers w ON w.id = b.voter_id
               WHERE b.vote_id=? ORDER BY b.cast_at""",
            (vote_id,),
        ).fetchall()
        yes = sum(1 for b in ballots if b["choice"] == "yes")
        no = sum(1 for b in ballots if b["choice"] == "no")
        abstain = sum(1 for b in ballots if b["choice"] == "abstain")
        return {
            **dict(row),
            "ballots": [dict(b) for b in ballots],
            "tally": {"yes": yes, "no": no, "abstain": abstain},
        }


@app.get("/transactions")
def list_transactions(status: str | None = None) -> list[dict]:
    with transaction() as conn:
        if status:
            rows = conn.execute(
                """SELECT * FROM money_transactions WHERE status=?
                   ORDER BY occurred_at DESC LIMIT 100""",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM money_transactions ORDER BY occurred_at DESC LIMIT 100"
            ).fetchall()
        return [dict(r) for r in rows]

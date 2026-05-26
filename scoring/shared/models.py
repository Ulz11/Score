from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

WorkerType = Literal["human", "agent"]
TaskStatus = Literal["open", "in_progress", "done", "cancelled", "stock", "danger"]
Choice = Literal["yes", "no", "abstain"]
TxnType = Literal["deposit", "withdrawal", "refund", "transfer", "loan_payment"]
KpiScope = Literal["worker", "team", "project"]
CommentTarget = Literal["task", "worker", "transaction", "meeting"]


class WorkerIn(BaseModel):
    name: str
    type: WorkerType
    handle: str
    base_salary: float = 0
    salary_currency: str = "USD"
    actor_id: Optional[str] = None


class SkillIn(BaseModel):
    skill_name: str
    level: int = Field(ge=0, le=100)
    notes: Optional[str] = None
    actor_id: Optional[str] = None


class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None
    actor_id: Optional[str] = None


class TaskIn(BaseModel):
    title: str
    description: Optional[str] = None
    weight: int = Field(ge=1, le=10)
    assignee_id: Optional[str] = None
    created_by: Optional[str] = None
    actor_id: Optional[str] = None


class TaskStatusIn(BaseModel):
    status: TaskStatus
    actor_id: Optional[str] = None


class KpiIn(BaseModel):
    scope: KpiScope
    scope_id: str
    period: str
    metric: str
    value: float
    target: float
    actor_id: Optional[str] = None


class PeerScoreIn(BaseModel):
    scorer_id: str
    target_task_id: str
    score: int = Field(ge=0, le=100)
    notes: Optional[str] = None


class CommentIn(BaseModel):
    author_id: str
    target_type: CommentTarget
    target_id: str
    body: str


class MeetingIn(BaseModel):
    title: str
    agenda: Optional[str] = None
    scheduled_at: str
    actor_id: Optional[str] = None


class VoteIn(BaseModel):
    proposal_text: str
    quorum_required: int = Field(ge=1)
    majority_threshold: float = 0.5
    linked_transaction_id: Optional[str] = None
    actor_id: Optional[str] = None


class BallotIn(BaseModel):
    voter_id: str
    choice: Choice


class TransactionIn(BaseModel):
    occurred_at: str
    amount: float
    currency: str = "USD"
    sender_party: str
    receiver_party: str
    location: Optional[str] = None
    payment_method: str
    transaction_type: TxnType
    actor_id: Optional[str] = None


class AuditIn(BaseModel):
    scope: str
    target_id: Optional[str] = None
    actor_id: Optional[str] = None

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

EventType = Literal["command", "http", "scan", "note", "system"]
PhaseName = Literal["recon", "enumeration", "hypothesis", "attempt", "post_check", "report"]
MemoryMode = Literal["summary", "window", "full"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ActivityEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: EventType
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionStartRequest(BaseModel):
    tenant_id: str
    user_id: str
    agent_id: str
    objective: str = "Complete the lab objective safely within allowed scope."
    target_scope: list[str] = Field(default_factory=list)
    policy_id: str = "lab-default"


class SessionRecord(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    agent_id: str
    objective: str
    target_scope: list[str]
    policy_id: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    current_phase: PhaseName = "recon"
    events: list[ActivityEvent] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    last_reasoning: str | None = None


class EventIngestRequest(BaseModel):
    events: list[ActivityEvent]


class ActionItem(BaseModel):
    title: str
    rationale: str
    done_criteria: str
    command: str | None = None


class SuggestRequest(BaseModel):
    user_message: str | None = None
    memory_mode: MemoryMode = "window"
    history_window: int = Field(default=12, ge=1, le=120)


class SessionSummary(BaseModel):
    session_id: str
    tenant_id: str
    user_id: str
    agent_id: str
    current_phase: PhaseName
    updated_at: datetime


class RetrievedContext(BaseModel):
    source: str
    score: float
    content: str


class SuggestResponse(BaseModel):
    session_id: str
    phase: PhaseName
    phase_confidence: float
    missing_artifacts: list[str]
    reasoning: str
    actions: list[ActionItem]
    retrieved_context: list[RetrievedContext]
    episode_summary: str


class ReindexResponse(BaseModel):
    indexed_chunks: int
    source_dir: str
    index_path: str

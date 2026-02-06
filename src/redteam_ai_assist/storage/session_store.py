from __future__ import annotations

from pathlib import Path
from threading import Lock
from uuid import uuid4

from redteam_ai_assist.core.models import (
    ActivityEvent,
    EventIngestRequest,
    SessionRecord,
    SessionStartRequest,
    utc_now,
)


class SessionStore:
    def __init__(self, store_dir: Path, max_events: int = 600) -> None:
        self.store_dir = store_dir
        self.max_events = max_events
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def create_session(self, request: SessionStartRequest) -> SessionRecord:
        session_id = f"{request.agent_id}-{uuid4().hex[:10]}"
        session = SessionRecord(
            session_id=session_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            agent_id=request.agent_id,
            objective=request.objective,
            target_scope=request.target_scope,
            policy_id=request.policy_id,
        )
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> SessionRecord | None:
        path = self._session_path(session_id)
        if not path.exists():
            return None
        payload = path.read_text(encoding="utf-8")
        return SessionRecord.model_validate_json(payload)

    def save_session(self, session: SessionRecord) -> None:
        session.updated_at = utc_now()
        with self._lock:
            self._session_path(session.session_id).write_text(
                session.model_dump_json(indent=2),
                encoding="utf-8",
            )

    def append_events(self, session_id: str, request: EventIngestRequest) -> SessionRecord:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")

        session.events.extend(request.events)
        if len(session.events) > self.max_events:
            session.events = session.events[-self.max_events :]
        self.save_session(session)
        return session

    def append_note(self, session_id: str, message: str) -> SessionRecord:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")

        session.notes.append(message)
        session.events.append(
            ActivityEvent(event_type="note", payload={"message": message, "source": "user"})
        )
        if len(session.events) > self.max_events:
            session.events = session.events[-self.max_events :]
        self.save_session(session)
        return session

    def _session_path(self, session_id: str) -> Path:
        return self.store_dir / f"{session_id}.json"

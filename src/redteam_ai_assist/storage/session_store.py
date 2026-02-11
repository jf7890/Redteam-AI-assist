from __future__ import annotations

import contextlib
import re
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


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class SessionStore:
    """File-based session store (MVP) with path-safe IDs + process-safe updates.

    Notes:
    - Session files are stored as JSON under store_dir.
    - Writes are atomic (write temp + replace).
    - Read-modify-write operations (append/update/delete) take an *inter-process* lock
      using flock on a per-session lock file.

    This makes the store much safer when running multiple API workers.
    """

    def __init__(self, store_dir: Path, max_events: int = 600) -> None:
        self.store_dir = store_dir
        self.max_events = max_events
        self.store_dir.mkdir(parents=True, exist_ok=True)

        # Thread-level lock (still useful inside one process).
        self._lock = Lock()

    def create_session(self, request: SessionStartRequest) -> SessionRecord:
        # Path-safe, opaque session id (do NOT embed agent_id).
        session_id = uuid4().hex
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
        self._validate_session_id(session_id)
        path = self._session_path(session_id)
        if not path.exists():
            return None
        payload = path.read_text(encoding="utf-8")
        return SessionRecord.model_validate_json(payload)

    def save_session(self, session: SessionRecord) -> None:
        """Persist full session to disk.

        Prefer using update_session() for concurrent-safe field updates.
        """

        self._validate_session_id(session.session_id)
        session.updated_at = utc_now()
        with self._session_lock(session.session_id):
            self._write_session_atomic(session)

    def update_session(self, session_id: str, mutator) -> SessionRecord:
        """Atomic read-modify-write update under a per-session lock."""

        self._validate_session_id(session_id)
        with self._session_lock(session_id):
            session = self.get_session(session_id)
            if session is None:
                raise KeyError(f"Session {session_id} not found")

            mutator(session)

            # Enforce event cap.
            if len(session.events) > self.max_events:
                session.events = session.events[-self.max_events :]

            session.updated_at = utc_now()
            self._write_session_atomic(session)
            return session

    def list_sessions(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[SessionRecord]:
        sessions: list[SessionRecord] = []
        for path in sorted(self.store_dir.glob("*.json")):
            # Skip obviously unsafe filenames.
            session_id = path.stem
            if not _SAFE_ID_RE.match(session_id):
                continue

            try:
                payload = path.read_text(encoding="utf-8")
                session = SessionRecord.model_validate_json(payload)
            except Exception:
                continue

            if tenant_id and session.tenant_id != tenant_id:
                continue
            if user_id and session.user_id != user_id:
                continue
            sessions.append(session)

        sessions.sort(key=lambda item: item.updated_at, reverse=True)
        return sessions[:limit]

    def append_events(self, session_id: str, request: EventIngestRequest) -> SessionRecord:
        def _mutate(session: SessionRecord) -> None:
            session.events.extend(request.events)

        return self.update_session(session_id, _mutate)

    def append_note(self, session_id: str, message: str) -> SessionRecord:
        def _mutate(session: SessionRecord) -> None:
            session.notes.append(message)
            session.events.append(
                ActivityEvent(event_type="note", payload={"message": message, "source": "user"})
            )

        return self.update_session(session_id, _mutate)

    def delete_session(self, session_id: str) -> bool:
        self._validate_session_id(session_id)
        path = self._session_path(session_id)
        if not path.exists():
            return False
        with self._session_lock(session_id):
            path.unlink(missing_ok=True)
            # Best-effort: remove lock file too.
            lock_path = self._lock_path(session_id)
            lock_path.unlink(missing_ok=True)
        return True

    def _write_session_atomic(self, session: SessionRecord) -> None:
        """Atomic write (tmp + replace). Caller should hold _session_lock()."""

        path = self._session_path(session.session_id)
        tmp_path = path.with_suffix(path.suffix + ".tmp")

        # Thread lock to avoid multiple threads writing temp file at the same time.
        with self._lock:
            tmp_path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
            tmp_path.replace(path)

    def _session_path(self, session_id: str) -> Path:
        """Return the on-disk path for a given session id.

        Includes a defense-in-depth check to prevent path traversal even if validation
        is bypassed.
        """

        filename = f"{session_id}.json"
        candidate = (self.store_dir / filename).resolve()
        root = self.store_dir.resolve()
        try:
            if not candidate.is_relative_to(root):
                raise ValueError("Unsafe session path")
        except AttributeError:
            # Python <3.9 fallback (not expected in this project)
            if root not in candidate.parents and candidate != root:
                raise ValueError("Unsafe session path")
        return candidate

    def _lock_path(self, session_id: str) -> Path:
        return self.store_dir / f".{session_id}.lock"

    @contextlib.contextmanager
    def _session_lock(self, session_id: str):
        """Inter-process lock using flock on a per-session lock file."""

        import fcntl

        lock_path = self._lock_path(session_id)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _validate_session_id(session_id: str) -> None:
        if not _SAFE_ID_RE.match(session_id):
            raise ValueError(
                "Invalid session_id. Only [A-Za-z0-9_-] allowed, max length 128."
            )

from pathlib import Path

from redteam_ai_assist.core.models import SessionStartRequest
from redteam_ai_assist.storage.session_store import SessionStore


def test_list_sessions_sorted_and_filtered(tmp_path: Path) -> None:
    store = SessionStore(store_dir=tmp_path / "sessions")
    session1 = store.create_session(
        SessionStartRequest(
            tenant_id="tenant-a",
            user_id="user-a",
            agent_id="agent-a",
            target_scope=["10.10.10.25"],
        )
    )
    session2 = store.create_session(
        SessionStartRequest(
            tenant_id="tenant-b",
            user_id="user-b",
            agent_id="agent-b",
            target_scope=["10.10.10.26"],
        )
    )
    store.append_note(session2.session_id, "latest update")

    sessions = store.list_sessions()
    assert sessions[0].session_id == session2.session_id
    assert sessions[1].session_id == session1.session_id

    filtered = store.list_sessions(tenant_id="tenant-a")
    assert len(filtered) == 1
    assert filtered[0].tenant_id == "tenant-a"


def test_delete_session(tmp_path: Path) -> None:
    store = SessionStore(store_dir=tmp_path / "sessions")
    session = store.create_session(
        SessionStartRequest(
            tenant_id="tenant-a",
            user_id="user-a",
            agent_id="agent-a",
            target_scope=["10.10.10.25"],
        )
    )
    assert store.get_session(session.session_id) is not None
    assert store.delete_session(session.session_id) is True
    assert store.get_session(session.session_id) is None
    assert store.delete_session(session.session_id) is False

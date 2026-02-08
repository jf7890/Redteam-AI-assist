from __future__ import annotations

from redteam_ai_assist.config import Settings
from redteam_ai_assist.core.models import (
    EventIngestRequest,
    ReindexResponse,
    SessionRecord,
    SessionSummary,
    SessionStartRequest,
    SuggestRequest,
    SuggestResponse,
)
from redteam_ai_assist.core.policy import PolicyGuard
from redteam_ai_assist.graph.workflow import AssistantWorkflow
from redteam_ai_assist.rag.embeddings import HashingEmbedder, HuggingFaceHostedEmbedder
from redteam_ai_assist.rag.indexer import build_rag_index
from redteam_ai_assist.rag.retriever import RagRetriever
from redteam_ai_assist.rag.store import JsonVectorStore
from redteam_ai_assist.services.llm_client import RedteamLLMClient
from redteam_ai_assist.storage.session_store import SessionStore


class AssistantService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ensure_directories()

        self.session_store = SessionStore(
            store_dir=settings.session_store_path,
            max_events=settings.max_events_per_session,
        )
        self.embedder = self._build_embedder()
        self.vector_store = JsonVectorStore(index_path=settings.rag_index_file)
        self.retriever = RagRetriever(embedder=self.embedder, store=self.vector_store)
        self.policy_guard = PolicyGuard(
            allowed_tools=settings.allowed_tools_set,
            blocklist_patterns=settings.blocklist_patterns_list,
        )
        self.llm_client = RedteamLLMClient(settings=settings)
        self.workflow = AssistantWorkflow(
            retriever=self.retriever,
            llm_client=self.llm_client,
            policy_guard=self.policy_guard,
            rag_top_k=settings.rag_top_k,
        )

    def start_session(self, request: SessionStartRequest) -> SessionRecord:
        return self.session_store.create_session(request)

    def ingest_events(self, session_id: str, request: EventIngestRequest) -> SessionRecord:
        return self.session_store.append_events(session_id=session_id, request=request)

    def get_session(self, session_id: str) -> SessionRecord:
        session = self.session_store.get_session(session_id=session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")
        return session

    def list_sessions(
        self,
        tenant_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> list[SessionSummary]:
        sessions = self.session_store.list_sessions(tenant_id=tenant_id, user_id=user_id, limit=limit)
        return [
            SessionSummary(
                session_id=item.session_id,
                tenant_id=item.tenant_id,
                user_id=item.user_id,
                agent_id=item.agent_id,
                current_phase=item.current_phase,
                updated_at=item.updated_at,
            )
            for item in sessions
        ]

    def delete_session(self, session_id: str) -> None:
        deleted = self.session_store.delete_session(session_id=session_id)
        if not deleted:
            raise KeyError(f"Session {session_id} not found")

    def suggest(self, session_id: str, request: SuggestRequest) -> SuggestResponse:
        if request.user_message:
            self.session_store.append_note(session_id=session_id, message=request.user_message)

        session = self.session_store.get_session(session_id=session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")

        state = self.workflow.run(
            session,
            memory_mode=request.memory_mode,
            history_window=request.history_window,
            phase_override=request.phase_override,
            rag_focus=request.rag_focus,
        )
        phase = state.get("phase", session.current_phase)
        should_persist_phase = not request.phase_override or request.persist_phase_override
        if should_persist_phase:
            session.current_phase = phase
        session.last_reasoning = state.get("reasoning")
        self.session_store.save_session(session)

        return SuggestResponse(
            session_id=session.session_id,
            phase=phase,
            phase_confidence=state.get("phase_confidence", 0.0),
            missing_artifacts=state.get("missing_artifacts", []),
            reasoning=state.get("reasoning", "No reasoning available."),
            actions=state.get("actions", []),
            retrieved_context=state.get("retrieved_context", []),
            episode_summary=state.get("episode_summary", "No episode summary available."),
        )

    def rebuild_rag_index(self) -> ReindexResponse:
        count = build_rag_index(
            source_dir=self.settings.rag_source_path,
            index_path=self.settings.rag_index_file,
            embedder=self.embedder,
            chunk_size=self.settings.rag_chunk_size,
        )
        return ReindexResponse(
            indexed_chunks=count,
            source_dir=str(self.settings.rag_source_path),
            index_path=str(self.settings.rag_index_file),
        )

    def _build_embedder(self):
        fallback = HashingEmbedder()
        if self.settings.hf_token:
            return HuggingFaceHostedEmbedder(
                token=self.settings.hf_token,
                model=self.settings.hf_embedding_model,
                fallback=fallback,
            )
        return fallback

    def _ensure_directories(self) -> None:
        self.settings.session_store_path.mkdir(parents=True, exist_ok=True)
        self.settings.rag_source_path.mkdir(parents=True, exist_ok=True)
        self.settings.rag_index_file.parent.mkdir(parents=True, exist_ok=True)

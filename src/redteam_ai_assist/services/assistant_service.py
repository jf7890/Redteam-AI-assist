from __future__ import annotations

import hashlib
import json

from redteam_ai_assist.config import Settings
from redteam_ai_assist.core.models import (
    CachedSuggest,
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
from redteam_ai_assist.rag.embeddings import CachedEmbedder, HashingEmbedder, HuggingFaceHostedEmbedder
from redteam_ai_assist.rag.indexer import build_rag_index
from redteam_ai_assist.rag.retriever import RagRetriever
from redteam_ai_assist.rag.store import JsonVectorStore
from redteam_ai_assist.services.llm_client import RedteamLLMClient
from redteam_ai_assist.storage.sqlite_cache import SQLiteCache
from redteam_ai_assist.storage.session_store import SessionStore


class AssistantService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._ensure_directories()

        # Lightweight local caches (file-based)
        self._embedding_cache = SQLiteCache(path=settings.embedding_cache_path)

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

        # MVP++: per-session suggest cache to avoid repeated LLM calls when the
        # effective context hasn't changed.
        fingerprint = self._compute_suggest_fingerprint(session, request)
        if session.cached_suggest and session.cached_suggest.fingerprint == fingerprint:
            try:
                return SuggestResponse.model_validate(session.cached_suggest.payload)
            except Exception:
                # Ignore broken cache entries.
                pass

        state = self.workflow.run(
            session,
            memory_mode=request.memory_mode,
            history_window=request.history_window,
            phase_override=request.phase_override,
            rag_focus=request.rag_focus,
        )

        phase = state.get("phase", session.current_phase)
        should_persist_phase = not request.phase_override or request.persist_phase_override

        response = SuggestResponse(
            session_id=session.session_id,
            phase=phase,
            phase_confidence=state.get("phase_confidence", 0.0),
            missing_artifacts=state.get("missing_artifacts", []),
            reasoning=state.get("reasoning", "No reasoning available."),
            actions=state.get("actions", []),
            retrieved_context=state.get("retrieved_context", []),
            episode_summary=state.get("episode_summary", "No episode summary available."),
        )

        # Persist phase/reasoning and cache *without* clobbering concurrently ingested events.
        def _mutate(record: SessionRecord) -> None:
            if should_persist_phase:
                record.current_phase = phase
            record.last_reasoning = state.get("reasoning")
            record.cached_suggest = CachedSuggest(
                fingerprint=fingerprint,
                payload=response.model_dump(mode="json"),
            )

        try:
            self.session_store.update_session(session_id=session_id, mutator=_mutate)
        except Exception:
            # Best-effort persistence; never block the API response.
            pass

        return response

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
            base = HuggingFaceHostedEmbedder(
                token=self.settings.hf_token,
                model=self.settings.hf_embedding_model,
                fallback=fallback,
            )

            ttl_seconds = int(self.settings.embedding_cache_ttl_days * 24 * 3600)
            return CachedEmbedder(
                base=base,
                cache=self._embedding_cache,
                namespace=f"hf:{self.settings.hf_embedding_model}",
                ttl_seconds=ttl_seconds,
                max_entries=self.settings.embedding_cache_max_entries,
            )

        # Hashing embedder is cheap; no need to cache.
        return fallback

    def _ensure_directories(self) -> None:
        self.settings.session_store_path.mkdir(parents=True, exist_ok=True)
        self.settings.cache_path.mkdir(parents=True, exist_ok=True)
        self.settings.embedding_cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings.rag_source_path.mkdir(parents=True, exist_ok=True)
        self.settings.rag_index_file.parent.mkdir(parents=True, exist_ok=True)

    def _compute_suggest_fingerprint(self, session: SessionRecord, request: SuggestRequest) -> str:
        """Compute a stable fingerprint for the effective /suggest inputs.

        If the fingerprint hasn't changed since the last call, we can safely
        return the cached suggestion and avoid calling the LLM.
        """

        # Keep it compact but robust enough to invalidate on meaningful changes.
        last_events = session.events[-25:]
        event_digest_material = [
            {
                "id": e.event_id,
                "type": e.event_type,
                "ts": e.timestamp.isoformat(),
                "payload": e.payload,
            }
            for e in last_events
        ]

        payload = {
            "v": "mvp++-suggest-v1",
            "session_id": session.session_id,
            "objective": session.objective,
            "target_scope": session.target_scope,
            "policy_id": session.policy_id,
            "current_phase": session.current_phase,
            "request": {
                "memory_mode": request.memory_mode,
                "history_window": request.history_window,
                "phase_override": request.phase_override,
                "rag_focus": request.rag_focus,
            },
            "events": event_digest_material,
            "rag_index_version": self.vector_store.index_version(),
        }

        raw = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, StateGraph

from redteam_ai_assist.core.models import ActionItem, PhaseName, RetrievedContext, SessionRecord
from redteam_ai_assist.core.phases import detect_phase, infer_missing_artifacts
from redteam_ai_assist.core.policy import PolicyGuard
from redteam_ai_assist.rag.retriever import RagRetriever
from redteam_ai_assist.services.llm_client import LLMContext, RedteamLLMClient
from redteam_ai_assist.telemetry.episode import build_episode_summary


class AssistantState(TypedDict, total=False):
    session: SessionRecord
    memory_mode: str
    history_window: int
    episode_summary: str
    phase: PhaseName
    phase_confidence: float
    missing_artifacts: list[str]
    retrieved_context: list[RetrievedContext]
    conversation_context: list[dict[str, str]]
    reasoning: str
    actions: list[ActionItem]


class AssistantWorkflow:
    def __init__(
        self,
        retriever: RagRetriever,
        llm_client: RedteamLLMClient,
        policy_guard: PolicyGuard,
        rag_top_k: int = 4,
    ) -> None:
        self.retriever = retriever
        self.llm_client = llm_client
        self.policy_guard = policy_guard
        self.rag_top_k = rag_top_k
        self._graph = self._build_graph()

    def run(self, session: SessionRecord, memory_mode: str = "window", history_window: int = 12) -> AssistantState:
        initial_state: AssistantState = {
            "session": session,
            "memory_mode": memory_mode,
            "history_window": history_window,
        }
        return self._graph.invoke(initial_state)

    def _build_graph(self):
        graph = StateGraph(AssistantState)
        graph.add_node("summarize", self._summarize_node)
        graph.add_node("classify", self._classify_phase_node)
        graph.add_node("retrieve", self._retrieve_rag_node)
        graph.add_node("memory", self._memory_node)
        graph.add_node("suggest", self._suggest_node)
        graph.add_node("policy", self._policy_node)

        graph.set_entry_point("summarize")
        graph.add_edge("summarize", "classify")
        graph.add_edge("classify", "retrieve")
        graph.add_edge("retrieve", "memory")
        graph.add_edge("memory", "suggest")
        graph.add_edge("suggest", "policy")
        graph.add_edge("policy", END)
        return graph.compile()

    def _summarize_node(self, state: AssistantState) -> AssistantState:
        session = state["session"]
        summary = build_episode_summary(session.events)
        return {"episode_summary": summary}

    def _classify_phase_node(self, state: AssistantState) -> AssistantState:
        session = state["session"]
        phase, confidence = detect_phase(session.events, session.current_phase)
        missing_artifacts = infer_missing_artifacts(session.events, phase)
        return {
            "phase": phase,
            "phase_confidence": confidence,
            "missing_artifacts": missing_artifacts,
        }

    def _retrieve_rag_node(self, state: AssistantState) -> AssistantState:
        session = state["session"]
        latest_note = session.notes[-1] if session.notes else ""
        query = (
            f"objective: {session.objective}\n"
            f"phase: {state['phase']}\n"
            f"latest_note: {latest_note}\n"
            f"episode_summary: {state['episode_summary']}"
        )
        chunks = self.retriever.query(query, top_k=self.rag_top_k)
        return {"retrieved_context": chunks}

    def _memory_node(self, state: AssistantState) -> AssistantState:
        session = state["session"]
        memory_mode = state.get("memory_mode", "window")
        history_window = state.get("history_window", 12)

        selected_events = session.events
        if memory_mode == "window":
            selected_events = session.events[-history_window:]
        elif memory_mode == "summary":
            selected_events = []

        conversation_context: list[dict[str, str]] = []
        for event in selected_events:
            payload = event.payload
            if event.event_type == "command":
                conversation_context.append(
                    {
                        "type": "command",
                        "content": str(payload.get("command", "")).strip(),
                        "summary": str(payload.get("stdout_summary", "")).strip(),
                    }
                )
            elif event.event_type == "http":
                conversation_context.append(
                    {
                        "type": "http",
                        "content": (
                            f"{payload.get('method', 'GET')} {payload.get('url', '')} "
                            f"status={payload.get('status_code', '')}"
                        ).strip(),
                        "summary": str(payload.get("summary", "")).strip(),
                    }
                )
            elif event.event_type == "note":
                conversation_context.append(
                    {
                        "type": "note",
                        "content": str(payload.get("message", "")).strip(),
                        "summary": "",
                    }
                )

        return {"conversation_context": conversation_context}

    def _suggest_node(self, state: AssistantState) -> AssistantState:
        session = state["session"]
        latest_note = session.notes[-1] if session.notes else ""
        llm_context = LLMContext(
            objective=session.objective,
            phase=state["phase"],
            episode_summary=state["episode_summary"],
            missing_artifacts=state["missing_artifacts"],
            retrieved_context=state.get("retrieved_context", []),
            target_scope=session.target_scope,
            user_message=latest_note,
            memory_mode=state.get("memory_mode", "window"),
            conversation_context=state.get("conversation_context", []),
        )
        reasoning, actions = self.llm_client.generate_actions(llm_context)
        return {"reasoning": reasoning, "actions": actions}

    def _policy_node(self, state: AssistantState) -> AssistantState:
        session = state["session"]
        sanitized = self.policy_guard.sanitize_actions(
            actions=state.get("actions", []),
            target_scope=session.target_scope,
        )
        return {"actions": sanitized}

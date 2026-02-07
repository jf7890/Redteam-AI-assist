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
    episode_summary: str
    phase: PhaseName
    phase_confidence: float
    missing_artifacts: list[str]
    retrieved_context: list[RetrievedContext]
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

    def run(self, session: SessionRecord) -> AssistantState:
        initial_state: AssistantState = {"session": session}
        return self._graph.invoke(initial_state)

    def _build_graph(self):
        graph = StateGraph(AssistantState)
        graph.add_node("summarize", self._summarize_node)
        graph.add_node("classify", self._classify_phase_node)
        graph.add_node("retrieve", self._retrieve_rag_node)
        graph.add_node("suggest", self._suggest_node)
        graph.add_node("policy", self._policy_node)

        graph.set_entry_point("summarize")
        graph.add_edge("summarize", "classify")
        graph.add_edge("classify", "retrieve")
        graph.add_edge("retrieve", "suggest")
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

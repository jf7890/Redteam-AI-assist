from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from redteam_ai_assist.config import Settings
from redteam_ai_assist.core.models import ActionItem, PhaseName, RetrievedContext
from redteam_ai_assist.core.phases import PHASE_DONE_CRITERIA


@dataclass(slots=True)
class LLMContext:
    objective: str
    phase: PhaseName
    episode_summary: str
    missing_artifacts: list[str]
    retrieved_context: list[RetrievedContext]
    target_scope: list[str]


class RedteamLLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider = settings.llm_provider.lower()
        self.client = self._build_client()

    def generate_actions(self, context: LLMContext) -> tuple[str, list[ActionItem]]:
        if self.client is None:
            return self._heuristic_reasoning(context), self._heuristic_actions(context.phase)

        try:
            reasoning, actions = self._llm_actions(context)
            if not actions:
                return self._heuristic_reasoning(context), self._heuristic_actions(context.phase)
            return reasoning, actions
        except Exception:
            return self._heuristic_reasoning(context), self._heuristic_actions(context.phase)

    def _build_client(self) -> OpenAI | None:
        if self.provider == "mock":
            return None

        api_key: str | None = None
        base_url = self.settings.llm_base_url
        if self.provider == "openai":
            api_key = self.settings.openai_api_key
        elif self.provider == "groq":
            api_key = self.settings.groq_api_key
            base_url = base_url or "https://api.groq.com/openai/v1"
        else:
            return None

        if not api_key:
            return None
        return OpenAI(api_key=api_key, base_url=base_url)

    def _llm_actions(self, context: LLMContext) -> tuple[str, list[ActionItem]]:
        rag_context = [
            {
                "source": item.source,
                "score": round(item.score, 4),
                "content": item.content[:500],
            }
            for item in context.retrieved_context
        ]

        prompt_payload = {
            "objective": context.objective,
            "phase": context.phase,
            "episode_summary": context.episode_summary,
            "missing_artifacts": context.missing_artifacts,
            "target_scope": context.target_scope,
            "retrieved_context": rag_context,
            "constraints": [
                "Lab-only coaching. Never provide real-world destructive instructions.",
                "Use only in-scope targets and allowed lab tools.",
                "Provide checklist-style next actions with completion criteria.",
                "No credential theft or persistence guidance.",
            ],
            "output_format": {
                "reasoning": "short string",
                "actions": [
                    {
                        "title": "string",
                        "rationale": "string",
                        "command": "string or null",
                        "done_criteria": "string",
                    }
                ],
            },
            "max_actions": 4,
        }

        response = self.client.chat.completions.create(
            model=self.settings.llm_model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a redteam coaching assistant for an isolated cyber range. "
                        "Return strict JSON only."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=True)},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(_extract_json(content))
        reasoning = str(payload.get("reasoning", "")).strip() or self._heuristic_reasoning(context)
        actions_raw = payload.get("actions", [])

        actions: list[ActionItem] = []
        if isinstance(actions_raw, list):
            for item in actions_raw[:4]:
                if not isinstance(item, dict):
                    continue
                actions.append(
                    ActionItem(
                        title=str(item.get("title", "")).strip() or "Next step",
                        rationale=str(item.get("rationale", "")).strip() or "Follow lab methodology.",
                        command=(
                            str(item.get("command", "")).strip()
                            if item.get("command") is not None
                            else None
                        ),
                        done_criteria=(
                            str(item.get("done_criteria", "")).strip()
                            or PHASE_DONE_CRITERIA[context.phase]
                        ),
                    )
                )
        return reasoning, actions

    def _heuristic_reasoning(self, context: LLMContext) -> str:
        missing_text = ", ".join(context.missing_artifacts) if context.missing_artifacts else "none"
        return (
            f"Phase inferred as {context.phase}. Missing artifacts: {missing_text}. "
            "Actions focus on collecting evidence and moving safely to the next stage."
        )

    def _heuristic_actions(self, phase: PhaseName) -> list[ActionItem]:
        templates: dict[PhaseName, list[dict[str, Any]]] = {
            "recon": [
                {
                    "title": "Build in-scope service inventory",
                    "rationale": "Inventory is required before deep enumeration.",
                    "command": "nmap -sV -Pn <TARGET_IN_SCOPE>",
                    "done_criteria": PHASE_DONE_CRITERIA["recon"],
                },
                {
                    "title": "Capture baseline notes",
                    "rationale": "Documenting early findings improves later hypothesis quality.",
                    "command": None,
                    "done_criteria": "At least one note per target is added to session timeline.",
                },
            ],
            "enumeration": [
                {
                    "title": "Deepen service-level inspection",
                    "rationale": "Service-specific enumeration reveals candidate weak points.",
                    "command": "gobuster dir -u http://<TARGET_IN_SCOPE> -w <WORDLIST_IN_LAB>",
                    "done_criteria": PHASE_DONE_CRITERIA["enumeration"],
                },
                {
                    "title": "Record notable responses",
                    "rationale": "Response patterns support stronger hypotheses.",
                    "command": None,
                    "done_criteria": "Top anomalies and related evidence refs are written as notes.",
                },
            ],
            "hypothesis": [
                {
                    "title": "Rank top attack hypotheses",
                    "rationale": "Prioritization avoids random tool usage.",
                    "command": None,
                    "done_criteria": PHASE_DONE_CRITERIA["hypothesis"],
                },
                {
                    "title": "Define validation plan per hypothesis",
                    "rationale": "Each hypothesis needs a measurable validation step.",
                    "command": None,
                    "done_criteria": "Every hypothesis has one in-scope verification method.",
                },
            ],
            "attempt": [
                {
                    "title": "Run lab-approved verification for hypothesis #1",
                    "rationale": "Execute the smallest safe validation first.",
                    "command": "<LAB_APPROVED_TOOL> <TARGET_IN_SCOPE> <SAFE_PARAMS>",
                    "done_criteria": PHASE_DONE_CRITERIA["attempt"],
                },
                {
                    "title": "Log result and branch decision",
                    "rationale": "Pass/fail evidence determines the next branch quickly.",
                    "command": None,
                    "done_criteria": "Result is marked pass/fail with timestamp and evidence ref.",
                },
            ],
            "post_check": [
                {
                    "title": "Validate impact boundaries in lab",
                    "rationale": "Impact must be demonstrated and bounded within scenario scope.",
                    "command": "whoami",
                    "done_criteria": PHASE_DONE_CRITERIA["post_check"],
                },
                {
                    "title": "Collect cleanup and reset notes",
                    "rationale": "Lab reproducibility depends on clean post-check handoff.",
                    "command": None,
                    "done_criteria": "Containment/reset notes are captured for instructor review.",
                },
            ],
            "report": [
                {
                    "title": "Compile finding timeline",
                    "rationale": "A clear timeline is required for grading and replay.",
                    "command": None,
                    "done_criteria": PHASE_DONE_CRITERIA["report"],
                },
                {
                    "title": "Attach evidence references",
                    "rationale": "Each finding must map to concrete evidence.",
                    "command": None,
                    "done_criteria": "Every finding includes at least one evidence reference.",
                },
            ],
        }
        return [ActionItem(**item) for item in templates[phase]]


def _extract_json(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped
    if "```" not in stripped:
        return stripped
    segments = [segment.strip() for segment in stripped.split("```") if segment.strip()]
    for segment in segments:
        if segment.startswith("{") and segment.endswith("}"):
            return segment
        if segment.startswith("json"):
            candidate = segment.removeprefix("json").strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
    return stripped

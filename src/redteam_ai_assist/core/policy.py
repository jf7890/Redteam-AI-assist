from __future__ import annotations

import re
from urllib.parse import urlparse

from redteam_ai_assist.core.models import ActionItem

IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HOST_PATTERN = re.compile(r"\b[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)+\b")


class PolicyGuard:
    def __init__(self, allowed_tools: set[str], blocklist_patterns: list[str]) -> None:
        self.allowed_tools = allowed_tools
        self.blocklist_patterns = blocklist_patterns

    def sanitize_actions(self, actions: list[ActionItem], target_scope: list[str]) -> list[ActionItem]:
        normalized_scope = {self._normalize_target(target) for target in target_scope}
        normalized_scope.discard("")
        sanitized: list[ActionItem] = []

        for action in actions:
            command = action.command
            reasons: list[str] = []

            if command:
                command_lower = command.lower()
                if any(pattern in command_lower for pattern in self.blocklist_patterns):
                    reasons.append("command removed by blocklist policy")
                    command = None

            if command:
                tool = self._extract_tool(command)
                if tool and tool not in self.allowed_tools:
                    reasons.append(f"tool '{tool}' is not in allowlist")
                    command = None

            if command and normalized_scope:
                out_of_scope_targets = self._find_out_of_scope_targets(command, normalized_scope)
                if out_of_scope_targets:
                    reasons.append(
                        f"target(s) {', '.join(sorted(out_of_scope_targets))} are out of session scope"
                    )
                    command = None

            if reasons:
                updated_rationale = f"{action.rationale} ({'; '.join(reasons)})"
                action = ActionItem(
                    title=action.title,
                    rationale=updated_rationale,
                    command=command,
                    done_criteria=action.done_criteria,
                )
            else:
                action = ActionItem(
                    title=action.title,
                    rationale=action.rationale,
                    command=command,
                    done_criteria=action.done_criteria,
                )

            sanitized.append(action)

        return sanitized

    @staticmethod
    def _extract_tool(command: str) -> str:
        first = command.strip().split(" ")[0].strip().lower()
        return first

    @staticmethod
    def _normalize_target(target: str) -> str:
        candidate = target.strip().lower()
        if not candidate:
            return ""
        if "://" in candidate:
            parsed = urlparse(candidate)
            return (parsed.hostname or "").lower()
        return candidate

    def _find_out_of_scope_targets(self, command: str, normalized_scope: set[str]) -> set[str]:
        candidates = set(IP_PATTERN.findall(command))
        candidates.update(HOST_PATTERN.findall(command))

        # Scope placeholders are always accepted.
        if "<target_in_scope>" in command.lower():
            return set()

        out_of_scope = set()
        for candidate in candidates:
            normalized_candidate = self._normalize_target(candidate)
            if normalized_candidate and normalized_candidate not in normalized_scope:
                out_of_scope.add(normalized_candidate)
        return out_of_scope

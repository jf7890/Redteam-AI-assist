from __future__ import annotations

from collections import Counter

from redteam_ai_assist.core.models import ActivityEvent


def build_episode_summary(events: list[ActivityEvent], max_events: int = 30) -> str:
    if not events:
        return "No events captured yet."

    recent = events[-max_events:]
    command_counter: Counter[str] = Counter()
    http_status_counter: Counter[int] = Counter()
    notes: list[str] = []

    for event in recent:
        payload = event.payload
        if event.event_type == "command":
            command = str(payload.get("command", "")).strip()
            if command:
                tool = command.split(" ")[0].lower()
                command_counter[tool] += 1
        if event.event_type == "http":
            status = payload.get("status_code")
            if isinstance(status, int):
                http_status_counter[status] += 1
        if event.event_type == "note":
            message = str(payload.get("message", "")).strip()
            if message:
                notes.append(message)

    top_tools = ", ".join(f"{tool}:{count}" for tool, count in command_counter.most_common(5)) or "none"
    status_mix = ", ".join(
        f"{status}:{count}" for status, count in sorted(http_status_counter.items())
    ) or "none"
    latest_notes = " | ".join(notes[-3:]) if notes else "none"

    return (
        f"Events analyzed: {len(recent)}. "
        f"Top command tools: {top_tools}. "
        f"HTTP status mix: {status_mix}. "
        f"Recent notes: {latest_notes}."
    )

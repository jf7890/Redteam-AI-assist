from __future__ import annotations

from collections import Counter

from redteam_ai_assist.core.models import ActivityEvent, PhaseName

PHASES: tuple[PhaseName, ...] = (
    "recon",
    "enumeration",
    "hypothesis",
    "attempt",
    "post_check",
    "report",
)

PHASE_DONE_CRITERIA: dict[PhaseName, str] = {
    "recon": "Service inventory exists for each in-scope target with evidence.",
    "enumeration": "At least one deep finding per discovered service is documented.",
    "hypothesis": "1-3 ranked hypotheses are written with validation plans.",
    "attempt": "Each hypothesis has a pass/fail validation result and timestamp.",
    "post_check": "Impact verification and containment notes are captured.",
    "report": "Timeline, findings, and evidence references are complete.",
}

PHASE_REQUIRED_ARTIFACTS: dict[PhaseName, list[str]] = {
    "recon": ["service_inventory"],
    "enumeration": ["service_inventory", "deep_service_findings"],
    "hypothesis": ["ranked_hypotheses"],
    "attempt": ["attempt_results"],
    "post_check": ["impact_validation"],
    "report": ["timeline_notes", "evidence_references"],
}

PHASE_PATTERNS: dict[PhaseName, tuple[str, ...]] = {
    "recon": ("nmap", "masscan", "naabu", "arp-scan", "netdiscover"),
    "enumeration": ("gobuster", "ffuf", "nikto", "enum4linux", "dirsearch"),
    "hypothesis": ("hypothesis", "possible weak point", "candidate issue"),
    "attempt": ("sqlmap", "hydra", "exploit", "metasploit", "poc"),
    "post_check": ("whoami", "id", "hostname", "proof", "verify impact"),
    "report": ("report", "summary", "timeline", "evidence"),
}

REPORT_KEYWORDS = ("report", "template", "timeline", "findings", "final notes")
RECON_KEYWORDS = ("recon", "reconnaissance", "inventory", "checklist")


def detect_phase(events: list[ActivityEvent], current_phase: PhaseName) -> tuple[PhaseName, float]:
    if not events:
        return current_phase, 0.4

    note_text = []
    for event in events[-10:]:
        if event.event_type == "note":
            note_text.append(str(event.payload.get("message", "")))
    note_text = " ".join(note_text).lower()
    if note_text:
        if any(keyword in note_text for keyword in REPORT_KEYWORDS):
            return "report", 0.9
        if any(keyword in note_text for keyword in RECON_KEYWORDS):
            return "recon", 0.85

    recent_text = []
    for event in events[-20:]:
        payload = event.payload
        recent_text.append(str(payload.get("command", "")))
        recent_text.append(str(payload.get("message", "")))
        recent_text.append(str(payload.get("summary", "")))
    text = " ".join(recent_text).lower()

    match_counts: Counter[PhaseName] = Counter()
    for phase, patterns in PHASE_PATTERNS.items():
        for pattern in patterns:
            if pattern in text:
                match_counts[phase] += 1

    if not match_counts:
        return current_phase, 0.45

    detected_phase = match_counts.most_common(1)[0][0]
    total_matches = sum(match_counts.values())
    confidence = min(0.95, 0.5 + (match_counts[detected_phase] / max(total_matches, 1)) * 0.5)
    return detected_phase, confidence


def infer_artifacts(events: list[ActivityEvent]) -> set[str]:
    artifact_flags: set[str] = set()

    for event in events:
        payload = event.payload
        command = str(payload.get("command", "")).lower()
        message = str(payload.get("message", "")).lower()

        if any(token in command for token in ("nmap", "masscan", "naabu")):
            artifact_flags.add("service_inventory")
        if any(token in command for token in ("gobuster", "ffuf", "nikto", "enum4linux")):
            artifact_flags.add("deep_service_findings")
        if "hypothesis" in message or payload.get("hypothesis"):
            artifact_flags.add("ranked_hypotheses")
        if any(token in command for token in ("sqlmap", "hydra", "exploit", "metasploit")):
            artifact_flags.add("attempt_results")
        if any(token in command for token in ("whoami", "id")) or "impact" in message:
            artifact_flags.add("impact_validation")
        if event.event_type == "note":
            artifact_flags.add("timeline_notes")
            if payload.get("evidence_ref"):
                artifact_flags.add("evidence_references")

    return artifact_flags


def infer_missing_artifacts(events: list[ActivityEvent], phase: PhaseName) -> list[str]:
    present = infer_artifacts(events)
    required = PHASE_REQUIRED_ARTIFACTS.get(phase, [])
    return [artifact for artifact in required if artifact not in present]

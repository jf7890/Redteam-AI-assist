from redteam_ai_assist.core.models import ActivityEvent
from redteam_ai_assist.core.phases import detect_phase, infer_missing_artifacts


def test_detect_phase_for_recon() -> None:
    events = [
        ActivityEvent(event_type="command", payload={"command": "nmap -sV -Pn 10.10.10.25"}),
    ]
    phase, confidence = detect_phase(events, current_phase="recon")
    assert phase == "recon"
    assert confidence >= 0.5


def test_detect_phase_for_enumeration() -> None:
    events = [
        ActivityEvent(
            event_type="command",
            payload={"command": "gobuster dir -u http://10.10.10.25 -w words.txt"},
        ),
    ]
    phase, _ = detect_phase(events, current_phase="recon")
    assert phase == "enumeration"


def test_infer_missing_artifacts() -> None:
    events = [
        ActivityEvent(event_type="command", payload={"command": "nmap -sV -Pn 10.10.10.25"}),
    ]
    missing = infer_missing_artifacts(events, phase="enumeration")
    assert "deep_service_findings" in missing

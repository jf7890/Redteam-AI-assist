from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from redteam_ai_assist.config import get_settings
from redteam_ai_assist.core.models import ActivityEvent, EventIngestRequest, SessionStartRequest, SuggestRequest
from redteam_ai_assist.services.assistant_service import AssistantService


def main() -> None:
    service = AssistantService(get_settings())
    session = service.start_session(
        SessionStartRequest(
            tenant_id="student1",
            user_id="student1-001",
            agent_id="student1-001",
            objective="Complete web lab objective and report findings.",
            target_scope=["10.10.10.25", "web01.lab.local"],
        )
    )

    service.ingest_events(
        session.session_id,
        EventIngestRequest(
            events=[
                ActivityEvent(
                    event_type="command",
                    payload={"command": "curl -I http://10.10.10.25", "exit_code": 0},
                ),
                ActivityEvent(
                    event_type="http",
                    payload={"method": "GET", "url": "http://10.10.10.25/admin", "status_code": 403},
                ),
            ]
        ),
    )
    suggestion = service.suggest(session.session_id, SuggestRequest())
    print(json.dumps(suggestion.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()

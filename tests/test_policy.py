from redteam_ai_assist.core.models import ActionItem
from redteam_ai_assist.core.policy import PolicyGuard


def test_policy_blocks_disallowed_tool() -> None:
    guard = PolicyGuard(
        allowed_tools={"nmap", "curl", "whoami"},
        blocklist_patterns=["rm -rf"],
    )
    actions = [
        ActionItem(
            title="Try shell",
            rationale="test",
            command="bash -c whoami",
            done_criteria="done",
        )
    ]
    sanitized = guard.sanitize_actions(actions, target_scope=["10.10.10.25"])
    assert sanitized[0].command is None
    assert "allowlist" in sanitized[0].rationale


def test_policy_blocks_out_of_scope_target() -> None:
    guard = PolicyGuard(
        allowed_tools={"nmap", "curl", "whoami"},
        blocklist_patterns=["rm -rf"],
    )
    actions = [
        ActionItem(
            title="Scan target",
            rationale="test",
            command="nmap -sV -Pn 10.10.10.99",
            done_criteria="done",
        )
    ]
    sanitized = guard.sanitize_actions(actions, target_scope=["10.10.10.25"])
    assert sanitized[0].command is None
    assert "out of session scope" in sanitized[0].rationale

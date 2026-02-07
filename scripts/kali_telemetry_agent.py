from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib import error, request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kali telemetry agent for Redteam AI Assist")
    parser.add_argument(
        "--base-url",
        default=os.getenv("BASE_URL", "http://127.0.0.1:8088"),
        help="Assistant API base URL",
    )
    parser.add_argument(
        "--session-id",
        default=os.getenv("SESSION_ID"),
        help="Session ID to attach events to",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("POLL_INTERVAL", "5")),
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--history-file",
        action="append",
        default=[],
        help="History file path (can be used multiple times)",
    )
    parser.add_argument(
        "--state-file",
        default=os.getenv(
            "AGENT_STATE_FILE",
            str(Path.home() / ".cache" / "redteam-ai-assist" / "history_offsets.json"),
        ),
        help="State file storing read offsets",
    )
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit")
    parser.add_argument("--verbose", action="store_true", help="Print debug logs")
    return parser.parse_args()


def default_history_files() -> list[Path]:
    home = Path.home()
    return [home / ".zsh_history", home / ".bash_history"]


def load_state(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {str(key): int(value) for key, value in payload.items()}
    except Exception:
        return {}


def save_state(path: Path, state: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=True, indent=2), encoding="utf-8")


def parse_history_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    # zsh history format: ": 1700000000:0;command"
    if text.startswith(": ") and ";" in text:
        return text.split(";", maxsplit=1)[-1].strip()
    return text


def read_new_commands(history_files: list[Path], offsets: dict[str, int]) -> list[str]:
    commands: list[str] = []
    for file_path in history_files:
        key = str(file_path)
        if not file_path.exists():
            continue

        current_offset = offsets.get(key, 0)
        file_size = file_path.stat().st_size
        if current_offset > file_size:
            current_offset = 0

        with file_path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(current_offset)
            lines = handle.readlines()
            offsets[key] = handle.tell()

        for line in lines:
            command = parse_history_line(line)
            if command:
                commands.append(command)
    return commands


def build_payload(commands: list[str]) -> dict[str, list[dict[str, object]]]:
    events = []
    for command in commands:
        events.append(
            {
                "event_type": "command",
                "payload": {
                    "command": command,
                    "source": "kali_telemetry_agent",
                },
            }
        )
    return {"events": events}


def post_events(base_url: str, session_id: str, commands: list[str], verbose: bool = False) -> None:
    if not commands:
        return

    payload = build_payload(commands)
    url = f"{base_url.rstrip('/')}/v1/sessions/{session_id}/events"
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            response.read()
        if verbose:
            print(f"[agent] posted {len(commands)} command events")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"[agent] HTTP error {exc.code}: {body}")
    except Exception as exc:
        print(f"[agent] post failed: {exc}")


def main() -> None:
    args = parse_args()
    if not args.session_id:
        raise SystemExit("--session-id is required (or set SESSION_ID env var)")

    history_files = [Path(item).expanduser() for item in args.history_file] or default_history_files()
    state_file = Path(args.state_file).expanduser()
    offsets = load_state(state_file)

    while True:
        commands = read_new_commands(history_files, offsets)
        post_events(args.base_url, args.session_id, commands, verbose=args.verbose)
        save_state(state_file, offsets)
        if args.once:
            break
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()

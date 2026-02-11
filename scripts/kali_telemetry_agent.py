from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
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
    parser.add_argument(
        "--auto-recon-target",
        action="append",
        default=[],
        help="Run one lightweight recon against target (can be used multiple times)",
    )
    parser.add_argument(
        "--auto-recon-nmap",
        action="store_true",
        help="Also run nmap in auto recon mode (off by default for web-only labs)",
    )
    parser.add_argument(
        "--auto-recon-full-port",
        action="store_true",
        help="Use full-port nmap in auto recon mode (requires --auto-recon-nmap)",
    )
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

        http_event = parse_http_from_command(command)
        if http_event:
            events.append({"event_type": "http", "payload": http_event})
    return {"events": events}


HTTP_URL_RE = re.compile(r"(https?://[^\s'\"\)]+)", re.IGNORECASE)


def parse_http_from_command(command: str) -> dict[str, object] | None:
    """Best-effort extraction of HTTP telemetry from common web tools.

    This helps the assistant reason about what the learner actually tried
    (GET/POST + which URL), even if the shell history only contains the command.
    """

    cmd = command.strip()
    if not cmd:
        return None

    tool = cmd.split()[0].lower()
    if tool not in {"curl", "wget", "sqlmap", "httpx", "whatweb"}:
        return None

    m = HTTP_URL_RE.search(cmd)
    if not m:
        return None

    url = m.group(1)
    method = "GET"
    summary = "parsed from command line"

    lowered = cmd.lower()
    if tool == "curl":
        # HEAD probe
        if re.search(r"(^|\s)--head(\s|$)", lowered) or re.search(r"(^|\s)-I(\s|$)", cmd):
            method = "HEAD"

        # Explicit method: -X/--request
        parts = cmd.split()
        for i, part in enumerate(parts):
            if part in {"-X", "--request"} and i + 1 < len(parts):
                method = parts[i + 1].upper()
                break

        # Data implies POST if method not explicitly set
        data_flags = (" -d", " --data", " --data-raw", " --form", " --form-string", " -F")
        if method == "GET" and any(flag in cmd or flag in lowered for flag in data_flags):
            method = "POST"

    elif tool == "wget":
        method = "GET"
    elif tool == "httpx":
        method = "GET"
        summary = "httpx probe parsed from command"
    elif tool == "whatweb":
        method = "GET"
        summary = "whatweb probe parsed from command"
    elif tool == "sqlmap":
        method = "GET"
        if " --data" in lowered or " -d" in lowered:
            method = "POST"
        if " --method" in lowered:
            parts = cmd.split()
            for i, part in enumerate(parts):
                if part == "--method" and i + 1 < len(parts):
                    method = parts[i + 1].upper()
                    break
        summary = "sqlmap target URL parsed from command"

    return {
        "method": method,
        "url": url,
        "status_code": 0,
        "summary": summary,
        "source": "kali_telemetry_agent.parsed",
    }


def post_payload(base_url: str, session_id: str, payload: dict[str, list[dict[str, object]]], verbose: bool = False) -> None:
    if not payload.get("events"):
        return

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
            print(f"[agent] posted {len(payload.get('events', []))} events")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        print(f"[agent] HTTP error {exc.code}: {body}")
    except Exception as exc:
        print(f"[agent] post failed: {exc}")


def post_events(base_url: str, session_id: str, commands: list[str], verbose: bool = False) -> None:
    if not commands:
        return
    payload = build_payload(commands)
    post_payload(base_url, session_id, payload, verbose=verbose)


def _run_command(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        return proc.returncode, output.strip()
    except Exception as exc:
        return 1, f"command failed: {exc}"


def _summarize_nmap_output(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    open_ports = [line for line in lines if "/tcp" in line and " open " in line]
    if open_ports:
        top = "; ".join(open_ports[:8])
        return f"Detected open services: {top}"
    return "No open services parsed from nmap output."


def build_auto_recon_events(
    target: str,
    full_port: bool = False,
    enable_nmap: bool = False,
) -> list[dict[str, object]]:
    """Lightweight web recon.

    Default is web-only (HTTP header probe). Nmap is optional.
    """

    events: list[dict[str, object]] = []

    if enable_nmap:
        nmap_args = ["nmap", "-sV", "-Pn", target]
        if full_port:
            nmap_args = ["nmap", "-sV", "-Pn", "-p-", target]

        nmap_rc, nmap_output = _run_command(nmap_args)
        events.append(
            {
                "event_type": "command",
                "payload": {
                    "command": " ".join(nmap_args),
                    "exit_code": nmap_rc,
                    "stdout_summary": _summarize_nmap_output(nmap_output),
                    "source": "kali_telemetry_agent.auto_recon",
                },
            }
        )

    for scheme in ("http", "https"):
        curl_args = ["curl", "-k", "-I", f"{scheme}://{target}"]
        curl_rc, curl_output = _run_command(curl_args)
        status_line = ""
        for line in curl_output.splitlines():
            if line.upper().startswith("HTTP/"):
                status_line = line.strip()
                break
        status_code = 0
        if status_line:
            parts = status_line.split()
            if len(parts) > 1 and parts[1].isdigit():
                status_code = int(parts[1])
        if curl_rc == 0 or status_code:
            events.append(
                {
                    "event_type": "http",
                    "payload": {
                        "method": "HEAD",
                        "url": f"{scheme}://{target}",
                        "status_code": status_code or 200,
                        "summary": status_line or "header probe completed",
                        "source": "kali_telemetry_agent.auto_recon",
                    },
                }
            )
            break

    return events


def main() -> None:
    args = parse_args()
    if not args.session_id:
        raise SystemExit("--session-id is required (or set SESSION_ID env var)")

    history_files = [Path(item).expanduser() for item in args.history_file] or default_history_files()
    state_file = Path(args.state_file).expanduser()
    offsets = load_state(state_file)

    if args.auto_recon_target:
        recon_events: list[dict[str, object]] = []
        for target in args.auto_recon_target:
            recon_events.extend(
                build_auto_recon_events(
                    target.strip(),
                    full_port=args.auto_recon_full_port,
                    enable_nmap=args.auto_recon_nmap,
                )
            )
        post_payload(args.base_url, args.session_id, {"events": recon_events}, verbose=args.verbose)
        if args.once:
            return

    while True:
        commands = read_new_commands(history_files, offsets)
        post_events(args.base_url, args.session_id, commands, verbose=args.verbose)
        save_state(state_file, offsets)
        if args.once:
            break
        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()

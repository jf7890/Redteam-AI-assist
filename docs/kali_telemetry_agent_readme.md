# Kali Telemetry Agent Usage

This agent runs on the client (Kali) machine and posts telemetry events to the Redteam AI Assist server.

It:
- reads shell history (bash/zsh) and posts `command` events
- parses HTTP targets from common web tools and posts `http` events
- optionally runs lightweight recon (`curl -I`, and `nmap` if enabled)

## Quick Start (download from server)

```bash
curl -fsSL http://<AI_SERVER>:8088/v1/agents/kali-telemetry-agent.py -o /tmp/kali_telemetry_agent.py
export BASE_URL="http://<AI_SERVER>:8088"
export SESSION_ID="<session_id>"
python /tmp/kali_telemetry_agent.py --poll-interval 5 --verbose
```

## Quick Start (repo clone)

```bash
python scripts/kali_telemetry_agent.py --poll-interval 5 --verbose
```

## Show Built-in Help

```bash
python /tmp/kali_telemetry_agent.py --help
```

## Environment Variables

These are optional and map to CLI flags:
- `BASE_URL` -> `--base-url`
- `SESSION_ID` -> `--session-id`
- `POLL_INTERVAL` -> `--poll-interval`
- `AGENT_STATE_FILE` -> `--state-file`

## CLI Options

- `--base-url`: API base URL (default: `http://127.0.0.1:8088`)
- `--session-id`: session ID to attach events to (required if not set via env)
- `--poll-interval`: seconds between history polls (default: `5`)
- `--history-file`: path to shell history (can be repeated)
- `--state-file`: path for history offsets (default: `~/.cache/redteam-ai-assist/history_offsets.json`)
- `--once`: run one polling cycle and exit
- `--verbose`: print debug logs
- `--auto-recon-target`: run lightweight recon against target (can be repeated)
- `--auto-recon-nmap`: enable `nmap` during auto recon
- `--auto-recon-full-port`: use full-port `nmap -p-` (requires `--auto-recon-nmap`)

## Examples

### 1) One-shot history upload

```bash
python /tmp/kali_telemetry_agent.py --once --verbose
```

### 2) Continuous mode every 10s

```bash
python /tmp/kali_telemetry_agent.py --poll-interval 10 --verbose
```

### 3) Use custom history files

```bash
python /tmp/kali_telemetry_agent.py \
  --history-file ~/.bash_history \
  --history-file ~/.zsh_history \
  --once --verbose
```

### 4) Auto recon (HEAD probe only)

```bash
python /tmp/kali_telemetry_agent.py \
  --auto-recon-target 172.16.100.128 \
  --auto-recon-target dvwa.local \
  --once --verbose
```

### 5) Auto recon with nmap

```bash
python /tmp/kali_telemetry_agent.py \
  --auto-recon-target 172.16.100.128 \
  --auto-recon-nmap \
  --once --verbose
```

### 6) Full-port nmap scan

```bash
python /tmp/kali_telemetry_agent.py \
  --auto-recon-target 172.16.100.128 \
  --auto-recon-nmap \
  --auto-recon-full-port \
  --once --verbose
```

## ALLOWED_TOOLS Examples

These examples show typical commands the assistant may propose when the tool is in `ALLOWED_TOOLS`.

```bash
# curl (HTTP HEAD)
curl -I http://172.16.100.128

# wget (simple fetch)
wget -S -O /tmp/index.html http://172.16.100.128

# httpx (probe)
httpx -u http://172.16.100.128

# whatweb (fingerprint)
whatweb http://172.16.100.128

# nikto (web scan)
nikto -h http://172.16.100.128

# nmap (service discovery)
nmap -sV -Pn 172.16.100.128

# ffuf (directory fuzz)
ffuf -u http://172.16.100.128/FUZZ -w /usr/share/wordlists/dirb/common.txt

# gobuster (dir brute force)
gobuster dir -u http://172.16.100.128 -w /usr/share/wordlists/dirb/common.txt

# feroxbuster (content discovery)
feroxbuster -u http://172.16.100.128 -w /usr/share/wordlists/dirb/common.txt

# dirsearch (content discovery)
dirsearch -u http://172.16.100.128 -w /usr/share/wordlists/dirb/common.txt

# sqlmap (targeted check)
sqlmap -u "http://172.16.100.128/vulnerable.php?id=1" --batch

# hydra (credential test - lab only)
hydra -l admin -P /usr/share/wordlists/rockyou.txt 172.16.100.128 http-post-form "/login.php:username=^USER^&password=^PASS^:F=incorrect"

# python / python3 / bash / sh (small helpers)
python -c "print('hello')"
python3 -c "print('hello')"
bash -c "echo hello"
sh -c "echo hello"
```

## Notes

- The agent runs on the client. The client must have any tools it executes (`curl`, `nmap`, etc.).
- If events are not appearing, ensure your shell history is written immediately:
  - bash: `export PROMPT_COMMAND='history -a; history -n; $PROMPT_COMMAND'`
  - zsh: `setopt INC_APPEND_HISTORY SHARE_HISTORY`

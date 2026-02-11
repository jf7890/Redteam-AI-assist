# New User Demo Flow (DVWA)

Goal: a beginner enters the lab and can follow AI guidance step-by-step without manual JSON crafting every time.

## 0) Start server

```bash
cd ~/Redteam-AI-assist
source .venv/bin/activate
uvicorn redteam_ai_assist.main:app --app-dir src --host 0.0.0.0 --port 8088 --reload
```

## 1) Create one session

```bash
BASE_URL="http://127.0.0.1:8088"

SESSION_ID=$(curl -s -X POST "$BASE_URL/v1/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id":"student1",
    "user_id":"student1-001",
    "agent_id":"student1-001",
    "objective":"Pentest DVWA lab safely and produce report",
    "target_scope":["172.16.100.128","dvwa.local"],
    "policy_id":"lab-default"
  }' | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

echo "$SESSION_ID"
```

Expected:
- You get a non-empty session id.

## 2) Bootstrap first telemetry automatically

```bash
python scripts/kali_telemetry_agent.py \
  --base-url "$BASE_URL" \
  --session-id "$SESSION_ID" \
  --auto-recon-target 172.16.100.128 \
  --auto-recon-target dvwa.local \
  --once --verbose
```

Expected:
- Agent posts an HTTP header probe event (`curl -I`).
- (Optional) enable nmap by adding `--auto-recon-nmap`.

Tip (make shell history visible to the agent quickly):
- zsh: `setopt INC_APPEND_HISTORY SHARE_HISTORY`
- bash: `export PROMPT_COMMAND='history -a; history -n; $PROMPT_COMMAND'`

## 3) Ask AI: what should I do first?

```bash
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message":"I just started. what should I do first?",
    "rag_focus":"recon",
    "phase_override":"recon",
    "persist_phase_override":false,
    "memory_mode":"window",
    "history_window":20
  }' | python -m json.tool
```

Expected:
- `phase` is recon.
- Actions are recon checklist-like and in-scope.

## 4) Execute one suggested step, then ask next

Run one action on Kali, then either:
- let `kali_telemetry_agent.py` pick up shell history, or
- manually POST one `command`/`http` event.

Then ask:

```bash
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message":"done. what next?",
    "rag_focus":"recon",
    "memory_mode":"window",
    "history_window":30
  }' | python -m json.tool
```

Expected:
- AI does not reset from zero; it uses session memory.
- Next steps depend on prior events in the same session.

## 5) Ask for report mode without breaking history

```bash
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message":"need report template now",
    "rag_focus":"report",
    "phase_override":"report",
    "persist_phase_override":false,
    "memory_mode":"window",
    "history_window":40
  }' | python -m json.tool
```

Expected:
- Current response goes report-oriented.
- Session phase is not permanently forced unless `persist_phase_override=true`.

## 6) Reload-safe resume

```bash
curl -s "$BASE_URL/v1/sessions/$SESSION_ID" | python -m json.tool
```

Expected:
- Session contains event history and notes.
- Frontend/client can restore conversation state after reload.

## 7) Cleanup when lab ends

```bash
curl -i -X DELETE "$BASE_URL/v1/sessions/$SESSION_ID"
```

Expected:
- `204 No Content`.

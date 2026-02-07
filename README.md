# Redteam AI Assist

LangGraph-based, multi-tenant redteam coaching assistant for your cyber range.

The assistant is designed for **lab-only** usage:
- Tracks a user session by `tenant_id`, `user_id`, `agent_id`.
- Ingests user telemetry events (command/http/notes/scan summary).
- Detects current phase (`recon -> enumeration -> hypothesis -> attempt -> post_check -> report`).
- Suggests next actions with completion criteria.
- Enforces scope/tool policy guard before returning commands.
- Uses RAG from local knowledge files and hosted embeddings (Hugging Face Inference API).

## 1. Architecture

Core components:
- `FastAPI` API for session lifecycle and suggestion endpoints.
- `LangGraph` workflow for summarize/classify/retrieve/suggest/policy steps.
- `SessionStore` file-based persistence (`runtime/sessions/*.json`).
- `RAG` using:
  - Source docs: `data/rag/knowledge_base/`
  - Vector index: `data/rag/index/index.jsonl`
- `PolicyGuard`:
  - Tool allowlist (`ALLOWED_TOOLS`)
  - Blocklist patterns (`BLOCKLIST_PATTERNS`)
  - Scope check against `target_scope`

## 2. Project Layout

```text
Redteam-AI-assist/
  src/redteam_ai_assist/
    api/routes.py
    core/{models.py,phases.py,policy.py}
    graph/workflow.py
    rag/{loader.py,embeddings.py,store.py,retriever.py,indexer.py}
    services/{assistant_service.py,llm_client.py}
    storage/session_store.py
    telemetry/episode.py
    main.py
  scripts/
    build_rag_index.py
    demo_session.py
    kali_telemetry_agent.py
  data/rag/knowledge_base/
    01_phase_checklist.md
    02_reporting_template.md
  tests/
    test_phases.py
    test_policy.py
  .env.example
  .gitignore
  requirements.txt
  pyproject.toml
  README.md
  docs/
    architecture.mmd
```

## 3. Setup (Debian)

Requirements:
- Python 3.11+
- `python3-venv` package

Install:

```bash
cd ~/Redteam-AI-assist
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 4. Environment Variables (`.env`)

Edit these first:
- `LLM_PROVIDER`: `mock` (default), `openai`, or `groq`.
- `LLM_MODEL`: model name for provider.
- `OPENAI_API_KEY` or `GROQ_API_KEY`: if using external LLM.
- `HF_TOKEN`: Hugging Face token for hosted embedding API.
- `HF_EMBEDDING_MODEL`: default `sentence-transformers/all-MiniLM-L6-v2`.

RAG path config:
- `RAG_SOURCE_DIR=data/rag/knowledge_base`
- `RAG_INDEX_PATH=data/rag/index/index.jsonl`

Policy config:
- `ALLOWED_TOOLS=...`
- `BLOCKLIST_PATTERNS=...`

## 5. RAG: Where to Put Files

Place your knowledge documents here:
- `data/rag/knowledge_base/*.md`
- `data/rag/knowledge_base/*.txt`

Examples of good content:
- Lab phase playbooks.
- Target-specific hints (for training scenario only).
- Reporting templates.
- Safe tool usage SOPs.

After updating files, rebuild index:

```bash
python scripts/build_rag_index.py
```

## 6. Run API Server (manual)

```bash
uvicorn redteam_ai_assist.main:app --app-dir src --host 0.0.0.0 --port 8088 --reload
```

Health check:

```bash
curl -s http://127.0.0.1:8088/health
```

## 7. API Usage

### Start session

```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id":"student1",
    "user_id":"student1-001",
    "agent_id":"student1-001",
    "objective":"Complete web lab objective",
    "target_scope":["10.10.10.25","web01.lab.local"],
    "policy_id":"lab-default"
  }'
```

### Ingest telemetry events

```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/events \
  -H "Content-Type: application/json" \
  -d '{
    "events":[
      {
        "event_type":"command",
        "payload":{"command":"nmap -sV -Pn 10.10.10.25","exit_code":0}
      },
      {
        "event_type":"http",
        "payload":{"method":"GET","url":"http://10.10.10.25/admin","status_code":403}
      }
    ]
  }'
```

### Get next-step suggestion

```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/suggest \
  -H "Content-Type: application/json" \
  -d '{"user_message":"Need next step"}'
```

### Suggest with session memory mode

The assistant supports memory policies per request:
- `summary`: only episode summary + RAG.
- `window`: last `history_window` events + summary + RAG.
- `full`: all session events + summary + RAG.

```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "user_message":"xong roi, tiep theo la gi?",
    "memory_mode":"window",
    "history_window":20
  }'
```

### Resume/list/delete session

```bash
# Get one session (for UI reload/resume)
curl -s http://127.0.0.1:8088/v1/sessions/<SESSION_ID>

# List latest sessions
curl -s "http://127.0.0.1:8088/v1/sessions?tenant_id=student1&limit=20"

# Teardown one session
curl -s -X DELETE http://127.0.0.1:8088/v1/sessions/<SESSION_ID> -i
```

### Rebuild RAG index from API

```bash
curl -s -X POST http://127.0.0.1:8088/v1/rag/reindex
```

## 8. LXC Deploy Guide (Debian on Proxmox)

This section assumes:
- Proxmox host, VLANs configured on a bridge (example `vmbr1` for lab).
- One LXC container dedicated for AI service on the same VLAN as router/orchestrator.
- You will not expose the AI API directly to student subnets.

### 8.1 Create LXC (Proxmox)

Recommended resources:
- 2-4 vCPU, 4-8GB RAM
- 20-40GB disk
- Unprivileged container
- Debian 12 template

Example `pct` create (adjust IDs/paths):

```bash
pct create 210 local:vztmpl/debian-12-standard_12.5-1_amd64.tar.zst \
  --hostname redteam-ai \
  --cores 4 --memory 8192 --swap 1024 \
  --rootfs local-lvm:20 \
  --unprivileged 1 \
  --net0 name=eth0,bridge=vmbr1,ip=192.168.50.10/24,gw=192.168.50.1
pct start 210
```

### 8.2 Install dependencies inside LXC

```bash
apt update
apt install -y python3-venv python3-pip nginx
useradd -r -m -d /opt/redteam-ai -s /usr/sbin/nologin redteam-ai
```

### 8.3 Deploy app in `/opt/redteam-ai`

```bash
cd /opt/redteam-ai
git clone <YOUR_REPO_URL> .
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY` or `GROQ_API_KEY`
- `HF_TOKEN` for hosted embeddings

Build RAG index:

```bash
python scripts/build_rag_index.py
```

### 8.4 Systemd service (recommended)

Create file `/etc/systemd/system/redteam-ai.service`:

```ini
[Unit]
Description=Redteam AI Assist API
After=network.target

[Service]
Type=simple
User=redteam-ai
WorkingDirectory=/opt/redteam-ai
EnvironmentFile=/opt/redteam-ai/.env
ExecStart=/opt/redteam-ai/.venv/bin/uvicorn redteam_ai_assist.main:app --app-dir src --host 127.0.0.1 --port 8088
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable service:

```bash
systemctl daemon-reload
systemctl enable --now redteam-ai
systemctl status redteam-ai --no-pager
```

### 8.5 Nginx reverse proxy (HTTP)

Create file `/etc/nginx/sites-available/redteam-ai`:

```nginx
server {
    listen 80;
    server_name _;  # set to your domain or IP

    location / {
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable site:

```bash
ln -s /etc/nginx/sites-available/redteam-ai /etc/nginx/sites-enabled/redteam-ai
nginx -t
systemctl reload nginx
```

### 8.6 Firewall + VLAN ACL (minimal safe baseline)

Goal: only router/orchestrator subnet can reach AI API.

Example `ufw` inside LXC (replace with your router subnet):

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow from 192.168.50.1 to any port 80 proto tcp
ufw allow from 192.168.50.1 to any port 8088 proto tcp
ufw enable
ufw status verbose
```

VLAN ACL rule on router (conceptual):
- Allow: `router_orchestrator_subnet -> redteam-ai:80/8088`
- Deny: `student_subnet -> redteam-ai:any`

## 9. Integration Notes for Your Infrastructure

Map your existing environment (example on Debian):
- Router: `/srv/cyber-range-router`
- Kali per-user packer: `/srv/packer-kali-user-space`
- Wazuh AIO packer: `/srv/packer-wazuh-AIO`

Recommended integration flow:
- On Kali boot/enroll, send telemetry events into this assistant with `agent_id`.
- Use `agent_id` + `tenant_id` as the same isolation key strategy you already use with Wazuh DLS.
- On lab teardown, call `DELETE /v1/sessions/{session_id}` for cleanup.

### 9.1 Kali telemetry agent (auto command ingestion)

Instead of posting events manually, run:

```bash
export BASE_URL="http://127.0.0.1:8088"
export SESSION_ID="<SESSION_ID>"
python scripts/kali_telemetry_agent.py --poll-interval 5 --verbose
```

This agent tails shell history (`~/.zsh_history`, `~/.bash_history`) and auto-posts new commands as `command` events.

Run one-shot debug cycle:

```bash
python scripts/kali_telemetry_agent.py --once --verbose
```

## 10. Run Tests

```bash
pytest -q
```

## 11. Safety Boundary

This project is intended for isolated cyber range labs.  
Do not use outside authorized environments.

## 12. Architecture Diagram

Mermaid diagram file: `docs/architecture.mmd`.

You can render it with:
- GitHub (auto-render in Markdown viewers that support Mermaid).
- `npx @mermaid-js/mermaid-cli -i docs/architecture.mmd -o docs/architecture.png`

## 13. RAG Debug Scenario

Step-by-step curl flow (recon vs report) to verify retrieval:
- `docs/rag_debug_scenario.md`

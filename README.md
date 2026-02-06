# Redteam AI Assist

LangGraph-based, multi-tenant redteam coaching assistant for your cyber range.

Project path: `D:\vannhan\Redteam-AI-assist`

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
```

## 3. Setup

Requirements:
- Python 3.11+
- PowerShell (Windows)

Install:

```powershell
cd D:\vannhan\Redteam-AI-assist
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
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

```powershell
python scripts\build_rag_index.py
```

## 6. Run API Server

```powershell
uvicorn redteam_ai_assist.main:app --app-dir src --host 0.0.0.0 --port 8088 --reload
```

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8088/health
```

## 7. API Usage

### Start session

```powershell
$body = @{
  tenant_id = "student1"
  user_id = "student1-001"
  agent_id = "student1-001"
  objective = "Complete web lab objective"
  target_scope = @("10.10.10.25","web01.lab.local")
  policy_id = "lab-default"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/v1/sessions -ContentType "application/json" -Body $body
```

### Ingest telemetry events

```powershell
$events = @{
  events = @(
    @{
      event_type = "command"
      payload = @{ command = "nmap -sV -Pn 10.10.10.25"; exit_code = 0 }
    },
    @{
      event_type = "http"
      payload = @{ method = "GET"; url = "http://10.10.10.25/admin"; status_code = 403 }
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/events" -ContentType "application/json" -Body $events
```

### Get next-step suggestion

```powershell
$suggest = @{ user_message = "Need next step" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/suggest" -ContentType "application/json" -Body $suggest
```

### Rebuild RAG index from API

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8088/v1/rag/reindex
```

## 8. Integration Notes for Your Infrastructure

Map your existing environment:
- Router: `D:\vannhan\cyber-range-router`
- Kali per-user packer: `D:\vannhan\packer-kali-user-space`
- Wazuh AIO packer: `D:\vannhan\packer-wazuh-AIO`

Recommended integration flow:
- On Kali boot/enroll, send telemetry events into this assistant with `agent_id`.
- Use `agent_id` + `tenant_id` as the same isolation key strategy you already use with Wazuh DLS.
- On lab teardown, delete session JSON files in `runtime/sessions/` by `session_id` if you want full cleanup.

## 9. Run Tests

```powershell
pytest -q
```

## 10. Safety Boundary

This project is intended for isolated cyber range labs.  
Do not use outside authorized environments.

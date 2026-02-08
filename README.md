# Redteam AI Assist

LangGraph-based, multi-tenant redteam coaching assistant for isolated cyber-range labs.

Lab-only stance:
- Per-session context via `tenant_id`, `user_id`, `agent_id`, `session_id`.
- Ingests command/http/note telemetry, infers phase (`recon -> enumeration -> hypothesis -> attempt -> post_check -> report`).
- Suggests next actions with done-criteria; enforces tool/scope policy; uses local RAG.

## 1. System Overview
- API-first service (FastAPI + LangGraph) returning JSON action suggestions.
- File-based SessionStore for persistence; Kali telemetry agent available for auto ingestion and light recon.
- Hybrid inference: local app; optional OpenAI/Groq LLMs; embeddings via HF Inference API with hashing fallback.

## 2. Architecture
- Workflow: summarize -> classify -> retrieve -> suggest -> policy.
- PolicyGuard: tool allowlist, blocklist patterns, target_scope validation.
- RAG over `data/rag/knowledge_base` with vector index `data/rag/index/index.jsonl`.
- Data flow: create session -> ingest events -> `/suggest` merges summary + memory (summary/window/full) + retrieved context -> policy sanitizes output.

## 3. Prompt & Guardrails
- System prompt: lab-only redteam coach, strict JSON output (`src/redteam_ai_assist/services/llm_client.py`).
- Payload fields: objective, phase, episode summary, missing artifacts, target_scope, user_message, memory_mode/window, rag_focus, conversation_context, retrieved_context.
- Heuristic fallback if LLM output is invalid; commands outside policy are nulled with reason.

## 4. RAG & Memory
- Sources: markdown/txt in `data/rag/knowledge_base/`; paragraph chunking; embeddings via HF Inference API or hashing.
- Store: JSONL + cosine similarity; rebuild index with `python scripts/build_rag_index.py`.
- Memory modes: `summary`, `window` (last N events), `full`; `rag_focus` (`auto|recon|report`) biases retrieval.

## 5. Limitations & Next Steps
- No dedicated prompt-injection firewall; relies on prompts + PolicyGuard.
- File-based storage and no auth/JWT; intended for internal ranges.
- Roadmap: authn/authz, DB store, eval metrics, richer metadata filters, learner UI.

## 6. Project Layout

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
    rag_debug_scenario.md
    new_user_demo_flow.md
```

## 7. Quick Setup (Debian)

Requirements: Python 3.11+, `python3-venv`.

```bash
cd ~/Redteam-AI-assist
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## 8. Environment

Key settings in `.env`:
- `LLM_PROVIDER` (`mock`|`openai`|`groq`), `LLM_MODEL`, `OPENAI_API_KEY`/`GROQ_API_KEY`.
- `HF_TOKEN`, `HF_EMBEDDING_MODEL` (`sentence-transformers/all-MiniLM-L6-v2` default).
- `RAG_SOURCE_DIR=data/rag/knowledge_base`, `RAG_INDEX_PATH=data/rag/index/index.jsonl`.
- `ALLOWED_TOOLS`, `BLOCKLIST_PATTERNS`.

## 9. Run Server

```bash
uvicorn redteam_ai_assist.main:app --app-dir src --host 0.0.0.0 --port 8088 --reload
curl -s http://127.0.0.1:8088/health
```

## 10. API Quickstart

- Create session:
```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"student1","user_id":"student1-001","agent_id":"student1-001","objective":"Complete web lab","target_scope":["10.10.10.25","web01.lab.local"],"policy_id":"lab-default"}'
```
- Ingest events:
```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/events \
  -H "Content-Type: application/json" \
  -d '{"events":[{"event_type":"command","payload":{"command":"nmap -sV -Pn 10.10.10.25","exit_code":0}}]}'
```
- Get suggestion (optionally `memory_mode`/`rag_focus` in body):
```bash
curl -s -X POST http://127.0.0.1:8088/v1/sessions/<SESSION_ID>/suggest \
  -H "Content-Type: application/json" \
  -d '{"user_message":"Need next step"}'
```
- Reindex RAG:
```bash
curl -s -X POST http://127.0.0.1:8088/v1/rag/reindex
```

## 11. Deployment (LXC/Proxmox)
- Create an unprivileged Debian 12 LXC/VM (2-4 vCPU, 4-8GB RAM) on the lab VLAN.
- Install `python3-venv python3-pip nginx`; create `/opt/redteam-ai` user/home.
- Deploy repo to `/opt/redteam-ai`, set up `.venv`, install requirements, copy `.env`, run `python scripts/build_rag_index.py`.
- Run via systemd (uvicorn on `127.0.0.1:8088`); optional nginx reverse proxy on port 80.
- Restrict access with VLAN ACL/firewall so only orchestrator/router subnet reaches the API.

## 12. Integration
- Use Kali telemetry agent for auto command ingestion or light recon: `python scripts/kali_telemetry_agent.py --poll-interval 5 --verbose`.
- Download the agent with curl (run on the Kali client):
```bash
curl -fsSL http://<AI_SERVER>:8088/v1/agents/kali-telemetry-agent.py -o /tmp/kali_telemetry_agent.py
BASE_URL=http://<AI_SERVER>:8088 SESSION_ID=<SESSION_ID> python /tmp/kali_telemetry_agent.py --poll-interval 5 --verbose
```
- Align `tenant_id`/`agent_id` with your range isolation; call `DELETE /v1/sessions/{session_id}` on teardown.
- More walkthroughs: `docs/new_user_demo_flow.md` and `docs/rag_debug_scenario.md`.

## 13. Tests

```bash
pytest -q
```

## 14. Safety Boundary

Lab-only. Do not expose to the Internet; treat telemetry/logs as sensitive; keep targets within authorized scope.

## 15. Documentation
- Architecture diagram: `docs/architecture.mmd`.
- RAG debug scenario: `docs/rag_debug_scenario.md`.
- Beginner demo flow: `docs/new_user_demo_flow.md`.

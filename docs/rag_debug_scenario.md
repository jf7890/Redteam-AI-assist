# RAG Debug Scenario (Recon vs Report)

Goal: verify that RAG retrieves the expected chunk when you mention "recon" or "report".

Prereqs:
- API server running (`uvicorn ...`).
- RAG index built: `python scripts/build_rag_index.py`.
- Knowledge base files exist:
  - `data/rag/knowledge_base/01_phase_checklist.md`
  - `data/rag/knowledge_base/02_reporting_template.md`
- Optional but recommended: set `HF_TOKEN` for better embeddings.

Set a base URL:

```bash
BASE_URL="http://127.0.0.1:8088"
```

## 1) Create session

```bash
SESSION_ID=$(curl -s -X POST "$BASE_URL/v1/sessions" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id":"student1",
    "user_id":"student1-001",
    "agent_id":"student1-001",
    "objective":"Complete web lab objective",
    "target_scope":["10.10.10.25","web01.lab.local"],
    "policy_id":"lab-default"
  }' | python -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "$SESSION_ID"
```

Expected:
- You get a non-empty `SESSION_ID`.

## 2) Ingest some recon events

```bash
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/events" \
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
  }' > /dev/null
```

## 3) Ask for recon guidance (force recon focus)

```bash
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message":"need recon checklist",
    "rag_focus":"recon",
    "phase_override":"recon",
    "persist_phase_override":false,
    "memory_mode":"window",
    "history_window":12
  }' | python -m json.tool
```

Expected (high-level):
- `episode_summary` includes `Recent notes: need recon checklist`.
- `retrieved_context` includes a source from `01_phase_checklist.md`.

Example snippet:

```json
{
  "retrieved_context": [
    {
      "source": ".../01_phase_checklist.md",
      "score": 0.0,
      "content": "## Recon..."
    }
  ]
}
```

## 4) Ask for report guidance (force report focus)

```bash
curl -s -X POST "$BASE_URL/v1/sessions/$SESSION_ID/suggest" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message":"need report template",
    "rag_focus":"report",
    "phase_override":"report",
    "persist_phase_override":false,
    "memory_mode":"window",
    "history_window":20
  }' | python -m json.tool
```

Expected (high-level):
- `episode_summary` includes `Recent notes: need report template`.
- `phase` should be `report`.
- `retrieved_context` includes a source from `02_reporting_template.md`.

## 4.1) Bootstrap automatic recon events (optional)

```bash
python scripts/kali_telemetry_agent.py \
  --base-url "$BASE_URL" \
  --session-id "$SESSION_ID" \
  --auto-recon-target 10.10.10.25 \
  --once --verbose
```

Expected:
- A new `command` event (`nmap -sV -Pn ...`) appears in session.
- A new `http` event may appear if header probe succeeds.

## 5) Validate session persistence (reload use-case)

```bash
curl -s "$BASE_URL/v1/sessions/$SESSION_ID" | python -m json.tool
```

Expected:
- Session returns with existing `events`, `notes`, `current_phase`.
- UI/client can restore context after reload using this endpoint.

## Troubleshooting

- If you see unrelated chunks:
  - Set `RAG_TOP_K=4` and `RAG_CHUNK_SIZE=1200` in `.env`.
  - Rebuild index: `python scripts/build_rag_index.py`.
  - Ensure `HF_TOKEN` is set for better embeddings.
- Query string is built from `objective + phase + focus + latest_note + episode_summary` in
  `src/redteam_ai_assist/graph/workflow.py` (`_retrieve_rag_node`).

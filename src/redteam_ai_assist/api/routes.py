from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse

from redteam_ai_assist.core.models import (
    EventIngestRequest,
    ReindexResponse,
    SessionRecord,
    SessionSummary,
    SessionStartRequest,
    SuggestRequest,
    SuggestResponse,
)
from redteam_ai_assist.services.assistant_service import AssistantService

router = APIRouter(prefix="/v1", tags=["assistant"])


def get_service(request: Request) -> AssistantService:
    return request.app.state.assistant_service


def get_repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def get_kali_agent_path() -> Path:
    return get_repo_root() / "scripts" / "kali_telemetry_agent.py"


@router.post("/sessions", response_model=SessionRecord, status_code=status.HTTP_201_CREATED)
def start_session(
    payload: SessionStartRequest,
    service: AssistantService = Depends(get_service),
) -> SessionRecord:
    return service.start_session(payload)


@router.post("/sessions/{session_id}/events", response_model=SessionRecord)
def ingest_events(
    session_id: str,
    payload: EventIngestRequest,
    service: AssistantService = Depends(get_service),
) -> SessionRecord:
    try:
        return service.ingest_events(session_id=session_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sessions/{session_id}", response_model=SessionRecord)
def get_session(
    session_id: str,
    service: AssistantService = Depends(get_service),
) -> SessionRecord:
    try:
        return service.get_session(session_id=session_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/sessions", response_model=list[SessionSummary])
def list_sessions(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    service: AssistantService = Depends(get_service),
) -> list[SessionSummary]:
    return service.list_sessions(tenant_id=tenant_id, user_id=user_id, limit=limit)


@router.post("/sessions/{session_id}/suggest", response_model=SuggestResponse)
def suggest(
    session_id: str,
    payload: SuggestRequest,
    service: AssistantService = Depends(get_service),
) -> SuggestResponse:
    try:
        return service.suggest(session_id=session_id, request=payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    service: AssistantService = Depends(get_service),
) -> Response:
    try:
        service.delete_session(session_id=session_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/rag/reindex", response_model=ReindexResponse)
def reindex_rag(service: AssistantService = Depends(get_service)) -> ReindexResponse:
    return service.rebuild_rag_index()


@router.get("/agents/kali-telemetry-agent.py")
def download_kali_agent() -> FileResponse:
    path = get_kali_agent_path()
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="kali_telemetry_agent.py not found")
    return FileResponse(path, filename="kali_telemetry_agent.py", media_type="text/x-python")

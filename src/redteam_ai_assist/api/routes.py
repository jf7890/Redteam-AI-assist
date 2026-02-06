from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from redteam_ai_assist.core.models import (
    EventIngestRequest,
    ReindexResponse,
    SessionRecord,
    SessionStartRequest,
    SuggestRequest,
    SuggestResponse,
)
from redteam_ai_assist.services.assistant_service import AssistantService

router = APIRouter(prefix="/v1", tags=["assistant"])


def get_service(request: Request) -> AssistantService:
    return request.app.state.assistant_service


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


@router.post("/rag/reindex", response_model=ReindexResponse)
def reindex_rag(service: AssistantService = Depends(get_service)) -> ReindexResponse:
    return service.rebuild_rag_index()

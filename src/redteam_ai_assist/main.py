from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from redteam_ai_assist.api.routes import router as assistant_router
from redteam_ai_assist.config import get_settings
from redteam_ai_assist.services.assistant_service import AssistantService


def create_app() -> FastAPI:
    settings = get_settings()
    service = AssistantService(settings=settings)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Multi-tenant redteam coaching assistant for an isolated cyber range. "
            "Uses LangGraph workflow + RAG + scope policy guard."
        ),
    )

    cors_origins = settings.cors_allow_origins_list
    if settings.cors_allow_all or cors_origins:
        allow_origins = ["*"] if settings.cors_allow_all else cors_origins
        allow_credentials = False if settings.cors_allow_all else settings.cors_allow_credentials
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allow_origins,
            allow_credentials=allow_credentials,
            allow_methods=settings.cors_allow_methods_list or ["*"],
            allow_headers=settings.cors_allow_headers_list or ["*"],
        )
    app.state.settings = settings
    app.state.assistant_service = service
    app.include_router(assistant_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app_env": settings.app_env}

    return app


app = create_app()

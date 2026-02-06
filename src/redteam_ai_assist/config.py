from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Redteam AI Assist"
    app_env: str = "dev"
    api_host: str = "0.0.0.0"
    api_port: int = 8088

    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    data_dir: Path = Path("data")
    runtime_dir: Path = Path("runtime")
    session_store_dir: Path = Path("runtime/sessions")

    llm_provider: str = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    openai_api_key: str | None = None
    groq_api_key: str | None = None

    hf_token: str | None = None
    hf_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    rag_source_dir: Path = Path("data/rag/knowledge_base")
    rag_index_path: Path = Path("data/rag/index/index.jsonl")
    rag_top_k: int = 4
    rag_chunk_size: int = 1200

    max_events_per_session: int = 600
    allowed_tools: str = (
        "nmap,masscan,naabu,gobuster,ffuf,nikto,curl,wget,sqlmap,hydra,"
        "netcat,nc,python,bash,sh,whoami,id,cat,ls,echo"
    )
    blocklist_patterns: str = (
        "rm -rf,shutdown,reboot,powershell Remove-Item,format c:,mkfs,dd if="
    )

    def to_abs_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        return self.project_root / path

    @property
    def session_store_path(self) -> Path:
        return self.to_abs_path(self.session_store_dir)

    @property
    def rag_source_path(self) -> Path:
        return self.to_abs_path(self.rag_source_dir)

    @property
    def rag_index_file(self) -> Path:
        return self.to_abs_path(self.rag_index_path)

    @property
    def allowed_tools_set(self) -> set[str]:
        return {tool.strip().lower() for tool in self.allowed_tools.split(",") if tool.strip()}

    @property
    def blocklist_patterns_list(self) -> list[str]:
        return [item.strip().lower() for item in self.blocklist_patterns.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        enable_decoding=False,
        extra="ignore",
    )

    anthropic_api_key: str = ""
    claude_model: str = "claude-3-5-haiku-latest"
    llm_provider: str = "ollama"
    enrichment_provider: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "minimax-m2.5:cloud"
    ollama_api_key: str = ""
    ollama_timeout_seconds: float = 120.0
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    openrouter_timeout_seconds: float = 120.0
    data_dir: Path = Path("backend/data")
    chroma_collection: str = "router_manuals"
    chunk_size: int = 900
    chunk_overlap: int = 150
    retrieval_top_k: int = 5
    max_distance: float = 0.65
    memory_turns: int = 5
    session_ttl_minutes: int = 120
    max_upload_mb: int = 25
    min_extracted_characters: int = 80
    enrichment_enabled: bool = True
    enrichment_batch_characters: int = 12000
    enrichment_poll_seconds: float = 2.0
    frontend_origins: list[str] = ["http://localhost:5173"]

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"ollama", "claude", "openrouter"}:
            raise ValueError("LLM_PROVIDER must be one of 'ollama', 'claude', or 'openrouter'.")
        return normalized

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def database_path(self) -> Path:
        return self.data_dir / "rag.sqlite3"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    return Settings()

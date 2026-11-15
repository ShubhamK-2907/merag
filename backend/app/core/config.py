"""Application settings, loaded once from environment variables (12-factor)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# provider -> (chat model, embedding model, embedding dimensions)
_PROVIDER_DEFAULTS = {
    # flash-lite answers in ~1s; full flash with default thinking took 15-60s+ per call on the free tier.
    "gemini": ("gemini-flash-lite-latest", "gemini-embedding-001", 768),
    "openai": ("gpt-4o-mini", "text-embedding-3-small", 1536),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_name: str = "MeRAG API"
    environment: str = "development"
    log_level: str = "INFO"
    # Comma-separated list of allowed browser origins for CORS.
    cors_origins: str = "http://localhost:5173"
    # Optional regex for preview deploys, e.g. r"https://merag-.*\.vercel\.app"
    cors_origin_regex: str | None = None

    # --- Auth ---
    jwt_secret: str = Field(default="dev-only-secret-change-me-please", min_length=16)
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 24  # 24h

    # --- MongoDB (users, chats, documents, vectors) ---
    mongodb_uri: str = "mongodb://localhost:27017/?directConnection=true"
    mongodb_db: str = "merag"
    vector_index_name: str = "chunk_vector_index"

    # --- LLMs ---
    # "gemini" works on Google AI Studio's free tier; "openai" needs a paid key.
    llm_provider: Literal["gemini", "openai"] = "gemini"
    google_api_key: str = ""
    openai_api_key: str = ""
    # Leave empty to use the provider defaults below.
    chat_model: str = ""
    # Gemini 3+ "thinking" depth. Each question makes ~4 calls, so keep this low for responsive answers.
    gemini_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"
    embedding_model: str = ""
    # Must match the Atlas vector index; changing it requires dropping that index.
    embedding_dimensions: int = 0
    tavily_api_key: str = ""

    # --- RAG tuning ---
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_k: int = 5
    max_rewrites: int = 1
    max_regenerations: int = 1
    history_window: int = 6
    max_upload_mb: int = 10

    @model_validator(mode="after")
    def _provider_defaults(self) -> "Settings":
        chat, embed, dims = _PROVIDER_DEFAULTS[self.llm_provider]
        self.chat_model = self.chat_model or chat
        self.embedding_model = self.embedding_model or embed
        self.embedding_dimensions = self.embedding_dimensions or dims
        return self

    @property
    def llm_api_key(self) -> str:
        return self.google_api_key if self.llm_provider == "gemini" else self.openai_api_key

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

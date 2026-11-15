"""Application settings, loaded once from environment variables (12-factor)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    openai_api_key: str = ""
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    tavily_api_key: str = ""

    # --- RAG tuning ---
    chunk_size: int = 1000
    chunk_overlap: int = 150
    retrieval_k: int = 5
    max_rewrites: int = 1
    max_regenerations: int = 1
    history_window: int = 6
    max_upload_mb: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

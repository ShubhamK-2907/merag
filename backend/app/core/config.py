"""Application settings, loaded once from environment variables (12-factor)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["gemini", "groq", "openai"]

_CHAT_DEFAULTS: dict[str, str] = {
    # flash-lite answers in ~1s; full flash with default thinking took 15-60s+ per call on the free tier.
    "gemini": "gemini-flash-lite-latest",
    "groq": "openai/gpt-oss-20b",
    "openai": "gpt-4o-mini",
}
# provider -> (embedding model, dimensions). Dimensions must match the Atlas vector index.
_EMBEDDING_DEFAULTS: dict[str, tuple[str, int]] = {
    "gemini": ("gemini-embedding-001", 768),
    "openai": ("text-embedding-3-small", 1536),
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
    # "gemini" and "groq" have free tiers; "openai" needs a paid key.
    llm_provider: Provider = "gemini"
    google_api_key: str = ""
    groq_api_key: str = ""
    openai_api_key: str = ""
    # Leave empty to use the provider defaults below.
    chat_model: str = ""
    # Comma-separated "provider:model" list tried in order when the primary model fails
    # (e.g. a free-tier 429). Each model has its own free quota, so this multiplies capacity:
    #   LLM_FALLBACKS=gemini:gemini-3.1-flash-lite,groq:openai/gpt-oss-20b
    llm_fallbacks: str = ""
    # Gemini 3+ "thinking" depth. Each question makes 2-3 calls, so keep this low for responsive answers.
    gemini_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"
    # Self-check of every answer against its sources: one extra LLM call per document/web answer.
    verify_answers: bool = True

    # --- Embeddings (independent of the chat provider; Groq has no embedding API) ---
    embedding_provider: Literal["", "gemini", "openai"] = ""  # empty: gemini, or openai if llm_provider=openai
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
        self.chat_model = self.chat_model or _CHAT_DEFAULTS[self.llm_provider]
        if not self.embedding_provider:
            self.embedding_provider = "openai" if self.llm_provider == "openai" else "gemini"
        embed, dims = _EMBEDDING_DEFAULTS[self.embedding_provider]
        self.embedding_model = self.embedding_model or embed
        self.embedding_dimensions = self.embedding_dimensions or dims
        self.fallback_models()  # fail fast on a malformed LLM_FALLBACKS
        return self

    def api_key_for(self, provider: str) -> str:
        return {"gemini": self.google_api_key, "groq": self.groq_api_key, "openai": self.openai_api_key}[provider]

    def fallback_models(self) -> list[tuple[Provider, str]]:
        out: list[tuple[Provider, str]] = []
        for item in filter(None, (p.strip() for p in self.llm_fallbacks.split(","))):
            provider, sep, model = item.partition(":")
            if not sep or provider not in _CHAT_DEFAULTS or not model:
                raise ValueError(f"LLM_FALLBACKS entry {item!r} must look like 'provider:model'")
            out.append((provider, model))  # type: ignore[arg-type]
        return out

    @property
    def llm_api_key(self) -> str:
        return self.api_key_for(self.llm_provider)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

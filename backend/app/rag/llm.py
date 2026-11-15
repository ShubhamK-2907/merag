"""Model factories. Centralised so models are swappable via env and mockable in tests."""

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import get_settings


@lru_cache
def get_chat_model() -> BaseChatModel:
    s = get_settings()
    return ChatOpenAI(model=s.chat_model, temperature=0, api_key=s.openai_api_key, max_retries=2, timeout=60)


@lru_cache
def get_embeddings() -> Embeddings:
    s = get_settings()
    return OpenAIEmbeddings(model=s.embedding_model, dimensions=s.embedding_dimensions, api_key=s.openai_api_key)

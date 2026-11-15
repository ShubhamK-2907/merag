"""Model factories. Centralised so the provider is a config switch and tests can mock it."""

from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.core.config import get_settings


@lru_cache
def get_chat_model() -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Retries cover free-tier 429s; low thinking keeps each of the ~4 calls per question around a second.
        return ChatGoogleGenerativeAI(
            model=s.chat_model,
            temperature=0,
            google_api_key=s.google_api_key,
            thinking_level=s.gemini_thinking_level,
            max_retries=3,
            timeout=45,
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=s.chat_model, temperature=0, api_key=s.openai_api_key, max_retries=2, timeout=60)


@lru_cache
def get_embeddings() -> Embeddings:
    s = get_settings()
    if s.llm_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=s.embedding_model, google_api_key=s.google_api_key, output_dimensionality=s.embedding_dimensions
        )
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=s.embedding_model, dimensions=s.embedding_dimensions, api_key=s.openai_api_key)

"""Model factories. Centralised so the provider is a config switch and tests can mock it.

Free tiers rate-limit per model, so the chat model is a *chain*: the primary model plus
optional fallbacks (LLM_FALLBACKS). When one model returns a 429 (or any error) the same
request is retried on the next one, so a demo keeps working after a quota runs out.
"""

from functools import lru_cache
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.core.config import get_settings


def _build_chat(provider: str, model: str, max_retries: int) -> BaseChatModel:
    s = get_settings()
    key = s.api_key_for(provider)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        # Low thinking keeps each call around a second on the free tier. Only Gemini 3+ accepts
        # thinking_level (2.x models reject it with a 400); 2.5 flash-lite does not think by default.
        thinking = {} if model.startswith("gemini-2") else {"thinking_level": s.gemini_thinking_level}
        return ChatGoogleGenerativeAI(
            model=model, temperature=0, google_api_key=key, max_retries=max_retries, timeout=45, **thinking
        )
    if provider == "groq":
        from langchain_groq import ChatGroq

        # gpt-oss / qwen are reasoning models: keep reasoning short and out of the answer text,
        # since reasoning tokens count against Groq's free tokens-per-minute budget.
        return ChatGroq(
            model=model,
            temperature=0,
            api_key=key,
            reasoning_effort="low" if "gpt-oss" in model else None,
            reasoning_format="hidden" if "qwen" in model else None,
            max_retries=max_retries,
            timeout=45,
        )
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=model, temperature=0, api_key=key, max_retries=max_retries, timeout=60)


class ChatChain:
    """Duck-types the slice of BaseChatModel the graph uses, with automatic model fallback."""

    def __init__(self, models: list[BaseChatModel]):
        if not models:
            raise ValueError("at least one chat model is required")
        self.models = models

    @staticmethod
    def _chain(runnables: list[Runnable]) -> Runnable:
        first, *rest = runnables
        return first.with_fallbacks(rest) if rest else first

    async def ainvoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        return await self._chain(self.models).ainvoke(input, config, **kwargs)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Runnable:
        return self._chain([m.with_structured_output(schema, **kwargs) for m in self.models])


@lru_cache
def get_chat_model() -> ChatChain:
    s = get_settings()
    chain = [(s.llm_provider, s.chat_model), *s.fallback_models()]
    chain = [(p, m) for p, m in chain if s.api_key_for(p)] or chain[:1]  # skip fallbacks with no key
    # With a fallback available, fail over at once instead of retrying a model that is out of quota;
    # only the last model in the chain retries.
    return ChatChain([_build_chat(p, m, max_retries=0 if i < len(chain) - 1 else 3) for i, (p, m) in enumerate(chain)])


@lru_cache
def get_embeddings() -> Embeddings:
    s = get_settings()
    if s.embedding_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=s.embedding_model, google_api_key=s.google_api_key, output_dimensionality=s.embedding_dimensions
        )
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=s.embedding_model, dimensions=s.embedding_dimensions, api_key=s.openai_api_key)

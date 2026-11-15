"""Thin async wrapper around Tavily web search (optional dependency)."""

import logging

from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.rag.state import WebResult

logger = logging.getLogger(__name__)


def is_enabled() -> bool:
    return bool(get_settings().tavily_api_key)


async def search(query: str, max_results: int = 5) -> list[WebResult]:
    if not is_enabled():
        return []
    from tavily import TavilyClient

    client = TavilyClient(api_key=get_settings().tavily_api_key)
    try:
        resp = await run_in_threadpool(client.search, query=query, max_results=max_results)
    except Exception:  # network/quota errors must not crash the chat
        logger.exception("Tavily search failed")
        return []
    return [
        WebResult(title=r.get("title", ""), url=r.get("url", ""), content=r.get("content", ""))
        for r in resp.get("results", [])
        if r.get("content")
    ]

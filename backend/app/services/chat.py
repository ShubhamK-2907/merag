"""Runs one chat turn through the RAG graph and streams progress as events.

Event protocol (Server-Sent Events, JSON payloads):
  step   {"node": str, "trace": [str]}   a graph node finished
  token  {"text": str}                   incremental answer text
  reset  {}                              discard streamed text (answer is being regenerated)
  done   {"message": MessageOut}         final persisted assistant message
  error  {"detail": str}
"""

import logging
from collections.abc import AsyncIterator
from typing import Any

from app.core.config import get_settings
from app.rag.graph import ANSWER_NODES, get_graph, history_to_messages
from app.schemas.chat import Source
from app.services import conversations, documents

logger = logging.getLogger(__name__)


def _error_detail(exc: Exception) -> str:
    """User-facing message; free-tier LLM quotas are the most common failure, so name them."""
    if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc) or "RateLimit" in type(exc).__name__:
        return "The AI model's free-tier rate limit was reached. Wait about a minute, then try again."
    return "The assistant hit an error. Please try again."


def _sources(state: dict) -> list[Source]:
    if state.get("route") == "search":
        return [
            Source(kind="web", title=r["title"] or r["url"], url=r["url"], snippet=r["content"][:300])
            for r in state.get("web_results", [])
        ]
    if state.get("route") == "index":
        return [
            Source(
                kind="document",
                title=c["filename"],
                document_id=c["document_id"],
                snippet=c["text"][:300],
                score=c["score"],
            )
            for c in state.get("chunks", [])
        ]
    return []


async def run_turn(user_id: str, conversation: dict, content: str) -> AsyncIterator[dict[str, Any]]:
    settings = get_settings()
    conversation_id = str(conversation["_id"])

    history_rows = await conversations.list_messages(conversation_id, limit=settings.history_window)
    await conversations.add_message(user_id, conversation_id, "user", content)
    await conversations.autotitle(conversation, content)

    inputs = {
        "user_id": user_id,
        "question": content,
        "history": history_to_messages(history_rows),
        "catalog": await documents.catalog(user_id),
        "trace": [],
    }

    final: dict[str, Any] = {"trace": []}
    try:
        async for mode, payload in get_graph().astream(inputs, stream_mode=["updates", "messages"]):
            if mode == "messages":
                chunk, meta = payload
                # .text flattens content blocks (Gemini 3 returns a list with thought signatures, not a str).
                text = chunk.text if meta.get("langgraph_node") in ANSWER_NODES else ""
                if text:
                    yield {"event": "token", "data": {"text": text}}
                continue
            for node, update in payload.items():
                update = update or {}
                final["trace"].extend(update.get("trace", []))
                final.update({k: v for k, v in update.items() if k != "trace"})
                yield {"event": "step", "data": {"node": node, "trace": update.get("trace", [])}}
                if (
                    node == "verify"
                    and update.get("faithful") is False
                    and (final.get("generations", 0) <= settings.max_regenerations)
                ):
                    yield {"event": "reset", "data": {}}
    except Exception as exc:
        logger.exception("RAG pipeline failed for conversation %s", conversation_id)
        yield {"event": "error", "data": {"detail": _error_detail(exc)}}
        return

    answer = final.get("answer") or "I couldn't produce an answer for that."
    saved = await conversations.add_message(
        user_id,
        conversation_id,
        "assistant",
        answer,
        route=final.get("route"),
        sources=[s.model_dump() for s in _sources(final)],
        trace=final["trace"],
    )
    yield {"event": "done", "data": {"message": conversations.to_message_out(saved).model_dump(mode="json")}}

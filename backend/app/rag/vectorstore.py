"""Per-user vector retrieval over the `chunks` collection.

Uses MongoDB Atlas `$vectorSearch` with a `user_id` pre-filter so a user can
only ever retrieve their own chunks. Falls back to an exact cosine scan when
the server has no vector search (plain local MongoDB).
"""

import logging
import math

from pymongo.errors import OperationFailure

from app.core.config import get_settings
from app.db.mongo import get_db, vector_index_queryable
from app.rag.llm import get_embeddings
from app.rag.state import Chunk

logger = logging.getLogger(__name__)

_FALLBACK_SCAN_LIMIT = 5000


async def search(user_id: str, query: str, k: int | None = None) -> list[Chunk]:
    settings = get_settings()
    k = k or settings.retrieval_k
    vector = await get_embeddings().aembed_query(query)
    # $vectorSearch on a missing/building index returns [] silently, so check readiness explicitly.
    if await vector_index_queryable():
        try:
            return await _atlas_search(user_id, vector, k)
        except OperationFailure as exc:
            logger.warning("$vectorSearch failed (%s); using cosine fallback", exc)
    return await _cosine_fallback(user_id, vector, k)


async def _atlas_search(user_id: str, vector: list[float], k: int) -> list[Chunk]:
    settings = get_settings()
    pipeline = [
        {
            "$vectorSearch": {
                "index": settings.vector_index_name,
                "path": "embedding",
                "queryVector": vector,
                "numCandidates": max(k * 20, 100),
                "limit": k,
                "filter": {"user_id": user_id},
            }
        },
        {
            "$project": {
                "document_id": 1,
                "filename": 1,
                "text": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]
    cursor = await get_db().chunks.aggregate(pipeline)
    return [_to_chunk(d, d["score"]) async for d in cursor]


async def _cosine_fallback(user_id: str, vector: list[float], k: int) -> list[Chunk]:
    cursor = get_db().chunks.find({"user_id": user_id}).limit(_FALLBACK_SCAN_LIMIT)
    scored = [(_cosine(vector, d["embedding"]), d) async for d in cursor]
    scored.sort(key=lambda t: t[0], reverse=True)
    return [_to_chunk(d, s) for s, d in scored[:k]]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _to_chunk(doc: dict, score: float) -> Chunk:
    return Chunk(
        id=str(doc["_id"]),
        document_id=str(doc["document_id"]),
        filename=doc["filename"],
        text=doc["text"],
        score=round(float(score), 4),
    )

"""MongoDB access: one async client per process, index bootstrap on startup.

MongoDB is the single datastore: users, conversations, messages, document
metadata AND chunk embeddings (queried with Atlas `$vectorSearch`). One managed
service keeps the deployment simple and lets every vector query be filtered by
`user_id` for tenant isolation.
"""

import logging
import time

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncMongoClient | None = None


def to_object_id(value: str) -> ObjectId | None:
    """Parse a path/id string; None for malformed ids (callers turn that into 404)."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def get_db() -> AsyncDatabase:
    if _client is None:
        raise RuntimeError("MongoDB client not initialised; call connect() first")
    return _client[get_settings().mongodb_db]


async def connect() -> None:
    global _client
    settings = get_settings()
    _client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True, serverSelectionTimeoutMS=10_000)
    await _client.admin.command("ping")
    logger.info("Connected to MongoDB database '%s'", settings.mongodb_db)


async def close() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def ensure_indexes() -> None:
    db = get_db()
    await db.users.create_index([("email", ASCENDING)], unique=True)
    await db.conversations.create_index([("user_id", ASCENDING), ("updated_at", DESCENDING)])
    await db.messages.create_index([("conversation_id", ASCENDING), ("created_at", ASCENDING)])
    await db.documents.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)])
    await db.chunks.create_index([("document_id", ASCENDING)])
    await db.chunks.create_index([("user_id", ASCENDING)])
    await _ensure_vector_index()


_INDEX_CHECK_TTL = 60.0
_index_state = {"queryable": False, "checked_at": float("-inf")}


async def vector_index_queryable() -> bool:
    """True once the Atlas vector index exists and is queryable (cached for 60s)."""
    now = time.monotonic()
    if _index_state["queryable"] or now - _index_state["checked_at"] < _INDEX_CHECK_TTL:
        return bool(_index_state["queryable"])
    _index_state["checked_at"] = now
    try:
        name = get_settings().vector_index_name
        async for ix in await get_db().chunks.list_search_indexes(name):
            _index_state["queryable"] = bool(ix.get("queryable"))
    except OperationFailure:
        _index_state["queryable"] = False  # not Atlas: exact-scan fallback
    return bool(_index_state["queryable"])


async def _ensure_vector_index() -> None:
    """Create the Atlas Vector Search index if the cluster supports it.

    On a plain (non-Atlas) MongoDB this fails gracefully and retrieval falls
    back to an in-process cosine scan (fine for local dev, not for scale).
    """
    settings = get_settings()
    db = get_db()
    if "chunks" not in await db.list_collection_names():
        await db.create_collection("chunks")
    try:
        existing = [ix["name"] async for ix in await db.chunks.list_search_indexes()]
        if settings.vector_index_name in existing:
            return
        model = SearchIndexModel(
            name=settings.vector_index_name,
            type="vectorSearch",
            definition={
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": settings.embedding_dimensions,
                        "similarity": "cosine",
                    },
                    {"type": "filter", "path": "user_id"},
                ]
            },
        )
        await db.chunks.create_search_index(model)
        logger.info("Created vector search index '%s'", settings.vector_index_name)
    except OperationFailure as exc:
        logger.warning(
            "Vector search index unavailable (%s). Using brute-force cosine fallback.",
            exc.details.get("errmsg") if exc.details else exc,
        )

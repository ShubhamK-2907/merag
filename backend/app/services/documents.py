"""Document lifecycle: ingest into the user's knowledge base, list, delete."""

from datetime import UTC, datetime

from app.db.mongo import get_db, to_object_id
from app.rag import ingestion
from app.schemas.document import DocumentOut


def to_document_out(doc: dict) -> DocumentOut:
    return DocumentOut(
        id=str(doc["_id"]),
        filename=doc["filename"],
        description=doc.get("description", ""),
        size_bytes=doc["size_bytes"],
        chunk_count=doc["chunk_count"],
        created_at=doc["created_at"],
    )


async def ingest(user_id: str, filename: str, data: bytes, description: str | None) -> dict:
    """Parse, chunk and embed first; write to the DB only once everything succeeded."""
    ext = ingestion.validate(filename, len(data))
    text = await ingestion.extract_text(ext, data)
    pieces = ingestion.split(text)
    prepared = await ingestion.embed(pieces)
    description = (description or "").strip() or await ingestion.describe(filename, text)

    db = get_db()
    doc = {
        "user_id": user_id,
        "filename": filename,
        "description": description[:300],
        "size_bytes": len(data),
        "chunk_count": len(prepared),
        "created_at": datetime.now(UTC),
    }
    doc["_id"] = (await db.documents.insert_one(doc)).inserted_id
    document_id = str(doc["_id"])
    try:
        await db.chunks.insert_many(
            [
                {
                    "user_id": user_id,
                    "document_id": document_id,
                    "filename": filename,
                    "chunk_index": c.index,
                    "text": c.text,
                    "embedding": c.embedding,
                }
                for c in prepared
            ]
        )
    except Exception:
        # Keep metadata and vectors consistent: no orphaned document rows.
        await db.documents.delete_one({"_id": doc["_id"]})
        await db.chunks.delete_many({"document_id": document_id})
        raise
    return doc


async def list_for_user(user_id: str) -> list[dict]:
    return await get_db().documents.find({"user_id": user_id}).sort("created_at", -1).to_list()


async def delete(user_id: str, document_id: str) -> bool:
    oid = to_object_id(document_id)
    if oid is None:
        return False
    db = get_db()
    result = await db.documents.delete_one({"_id": oid, "user_id": user_id})
    if result.deleted_count:
        await db.chunks.delete_many({"document_id": document_id, "user_id": user_id})
    return bool(result.deleted_count)


async def catalog(user_id: str) -> str:
    """One line per document; tells the router what the knowledge base covers."""
    docs = await list_for_user(user_id)
    return "\n".join(f"- {d['filename']}: {d.get('description', '')}" for d in docs)

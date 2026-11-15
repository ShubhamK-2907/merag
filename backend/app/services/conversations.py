"""Conversation + message persistence. Every query is scoped by user_id."""

from datetime import UTC, datetime

from app.db.mongo import get_db, to_object_id
from app.schemas.chat import ConversationOut, MessageOut

DEFAULT_TITLE = "New chat"


def to_conversation_out(doc: dict) -> ConversationOut:
    return ConversationOut(
        id=str(doc["_id"]), title=doc["title"], created_at=doc["created_at"], updated_at=doc["updated_at"]
    )


def to_message_out(doc: dict) -> MessageOut:
    return MessageOut(
        id=str(doc["_id"]),
        role=doc["role"],
        content=doc["content"],
        route=doc.get("route"),
        sources=doc.get("sources", []),
        trace=doc.get("trace", []),
        created_at=doc["created_at"],
    )


async def create(user_id: str, title: str | None = None) -> dict:
    now = datetime.now(UTC)
    doc = {"user_id": user_id, "title": (title or DEFAULT_TITLE).strip(), "created_at": now, "updated_at": now}
    doc["_id"] = (await get_db().conversations.insert_one(doc)).inserted_id
    return doc


async def list_for_user(user_id: str, limit: int = 100) -> list[dict]:
    cursor = get_db().conversations.find({"user_id": user_id}).sort("updated_at", -1).limit(limit)
    return await cursor.to_list()


async def get(user_id: str, conversation_id: str) -> dict | None:
    oid = to_object_id(conversation_id)
    if oid is None:
        return None
    return await get_db().conversations.find_one({"_id": oid, "user_id": user_id})


async def rename(user_id: str, conversation_id: str, title: str) -> dict | None:
    oid = to_object_id(conversation_id)
    if oid is None:
        return None
    return await get_db().conversations.find_one_and_update(
        {"_id": oid, "user_id": user_id},
        {"$set": {"title": title.strip(), "updated_at": datetime.now(UTC)}},
        return_document=True,
    )


async def delete(user_id: str, conversation_id: str) -> bool:
    oid = to_object_id(conversation_id)
    if oid is None:
        return False
    db = get_db()
    result = await db.conversations.delete_one({"_id": oid, "user_id": user_id})
    if result.deleted_count:
        await db.messages.delete_many({"conversation_id": conversation_id})
    return bool(result.deleted_count)


async def list_messages(conversation_id: str, limit: int | None = None) -> list[dict]:
    """Chronological messages; with `limit`, the most recent `limit` ones."""
    coll = get_db().messages
    if limit is None:
        return await coll.find({"conversation_id": conversation_id}).sort("created_at", 1).to_list()
    recent = await coll.find({"conversation_id": conversation_id}).sort("created_at", -1).limit(limit).to_list()
    return list(reversed(recent))


async def add_message(user_id: str, conversation_id: str, role: str, content: str, **extra) -> dict:
    now = datetime.now(UTC)
    doc = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "role": role,
        "content": content,
        "created_at": now,
        **extra,
    }
    db = get_db()
    doc["_id"] = (await db.messages.insert_one(doc)).inserted_id
    await db.conversations.update_one({"_id": to_object_id(conversation_id)}, {"$set": {"updated_at": now}})
    return doc


async def autotitle(conversation: dict, first_message: str) -> None:
    if conversation["title"] != DEFAULT_TITLE:
        return
    title = " ".join(first_message.split())[:60]
    await get_db().conversations.update_one({"_id": conversation["_id"]}, {"$set": {"title": title}})

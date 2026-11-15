import json

from fastapi import APIRouter, HTTPException, Request, Response, status
from sse_starlette.sse import EventSourceResponse

from app.api.deps import CurrentUser, uid
from app.core.rate_limit import limiter
from app.schemas.chat import (
    ConversationCreate,
    ConversationOut,
    ConversationRename,
    MessageOut,
    SendMessageRequest,
)
from app.services import chat, conversations

router = APIRouter(prefix="/conversations", tags=["conversations"])


async def _owned(user: dict, conversation_id: str) -> dict:
    conv = await conversations.get(uid(user), conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conv


@router.get("", response_model=list[ConversationOut])
async def list_conversations(user: CurrentUser):
    return [conversations.to_conversation_out(c) for c in await conversations.list_for_user(uid(user))]


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(user: CurrentUser, body: ConversationCreate | None = None):
    conv = await conversations.create(uid(user), body.title if body else None)
    return conversations.to_conversation_out(conv)


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: str, body: ConversationRename, user: CurrentUser):
    conv = await conversations.rename(uid(user), conversation_id, body.title)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return conversations.to_conversation_out(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, user: CurrentUser):
    if not await conversations.delete(uid(user), conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(conversation_id: str, user: CurrentUser):
    conv = await _owned(user, conversation_id)
    return [conversations.to_message_out(m) for m in await conversations.list_messages(str(conv["_id"]))]


@router.post("/{conversation_id}/messages")
@limiter.limit("20/minute")
async def send_message(request: Request, conversation_id: str, body: SendMessageRequest, user: CurrentUser):
    """Stream the assistant's answer as Server-Sent Events (see services/chat.py)."""
    conv = await _owned(user, conversation_id)

    async def events():
        async for evt in chat.run_turn(uid(user), conv, body.content.strip()):
            yield {"event": evt["event"], "data": json.dumps(evt["data"])}

    # X-Accel-Buffering disables proxy buffering so tokens reach the browser immediately.
    return EventSourceResponse(events(), ping=15, headers={"X-Accel-Buffering": "no"})

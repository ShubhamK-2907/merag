from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Route = Literal["index", "general", "search"]


class Source(BaseModel):
    kind: Literal["document", "web"]
    title: str
    snippet: str
    document_id: str | None = None
    url: str | None = None
    score: float | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=120)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    route: Route | None = None
    sources: list[Source] = []
    trace: list[str] = []
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

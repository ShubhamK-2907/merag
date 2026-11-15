from datetime import datetime

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    filename: str
    description: str
    size_bytes: int
    chunk_count: int
    created_at: datetime

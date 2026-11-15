"""Document ingestion: parse -> chunk -> embed. Pure functions, no DB access."""

import io
from dataclasses import dataclass
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.rag import prompts
from app.rag.llm import get_chat_model, get_embeddings

ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
_EMBED_BATCH = 64


class IngestionError(ValueError):
    """Raised for user-fixable problems (bad type, empty text, too large)."""


@dataclass
class PreparedChunk:
    index: int
    text: str
    embedding: list[float]


def validate(filename: str, size: int) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise IngestionError(f"Unsupported file type '{ext}'. Use PDF, TXT or MD.")
    limit = get_settings().max_upload_mb * 1024 * 1024
    if size > limit:
        raise IngestionError(f"File is larger than {get_settings().max_upload_mb} MB.")
    if size == 0:
        raise IngestionError("File is empty.")
    return ext


def _extract_text_sync(ext: str, data: bytes) -> str:
    if ext == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise IngestionError("Could not read this PDF. Is it encrypted or corrupted?") from exc
    return data.decode("utf-8", errors="replace")


async def extract_text(ext: str, data: bytes) -> str:
    text = await run_in_threadpool(_extract_text_sync, ext, data)
    text = text.replace("\x00", "").strip()
    if len(text) < 20:
        raise IngestionError("No extractable text found (scanned PDFs need OCR first).")
    return text


def split(text: str) -> list[str]:
    s = get_settings()
    splitter = RecursiveCharacterTextSplitter(chunk_size=s.chunk_size, chunk_overlap=s.chunk_overlap)
    return [c for c in splitter.split_text(text) if c.strip()]


async def embed(chunks: list[str]) -> list[PreparedChunk]:
    embedder = get_embeddings()
    out: list[PreparedChunk] = []
    for start in range(0, len(chunks), _EMBED_BATCH):
        batch = chunks[start : start + _EMBED_BATCH]
        vectors = await embedder.aembed_documents(batch)
        out.extend(PreparedChunk(start + i, t, v) for i, (t, v) in enumerate(zip(batch, vectors, strict=True)))
    return out


async def describe(text: str) -> str:
    """Auto-generate a catalog description used by the router."""
    msg = await get_chat_model().ainvoke(prompts.SUMMARIZE_DOC.format(excerpt=text[:2500]))
    return str(msg.content).strip()[:300]

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile, status

from app.api.deps import CurrentUser, uid
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.rag.ingestion import IngestionError
from app.schemas.document import DocumentOut
from app.services import documents

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: CurrentUser):
    return [documents.to_document_out(d) for d in await documents.list_for_user(uid(user))]


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    user: CurrentUser,
    file: UploadFile = File(...),
    description: str | None = Form(default=None, max_length=300),
):
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)  # read at most limit+1 bytes: never buffer huge uploads
    try:
        doc = await documents.ingest(uid(user), file.filename or "document", data, description)
    except IngestionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except Exception as exc:
        logger.exception("Ingestion failed for %s", file.filename)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not process the document. Try again.") from exc
    return documents.to_document_out(doc)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(document_id: str, user: CurrentUser):
    if not await documents.delete(uid(user), document_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import FileResponse

from app.config import UPLOAD_DIR
from app.schemas.document import (
    DocumentResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    DocumentStatusResponse,
)
from app.services.document_service import document_service, resolve_within
from app.services.storage_service import storage_service
from app.utils.security import get_current_active_user

logger = logging.getLogger("docintel.documents")

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/process", response_model=DocumentUploadResponse, status_code=202)
async def process_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    """Accepts an upload and queues it for asynchronous processing.

    Returns immediately with the document and job identifiers; the OCR/AI
    pipeline runs in a worker (never inside this request).
    """
    return await document_service.create_upload(file, current_user, background_tasks)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    type: Optional[str] = Query(None, description="Filter by document type (Invoice, Contract, Identity, Form)"),
    status: Optional[str] = Query(None, description="Filter by status (Verified, Flagged)"),
    search: Optional[str] = Query(None, description="Search term for filename, document_id, or text"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_active_user),
):
    return await document_service.list_documents(
        current_user=current_user,
        doc_type=type,
        status=status,
        search=search,
        page=page,
        limit=limit,
    )


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(document_id: str, current_user: dict = Depends(get_current_active_user)):
    """Authenticated, ownership-scoped processing status (safe error info only)."""
    status = await document_service.get_document_status(document_id, current_user)
    if not status:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    return status


@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse, status_code=202)
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user),
):
    result = await document_service.reprocess_document(document_id, current_user, background_tasks)
    if not result:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    return result


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, current_user: dict = Depends(get_current_active_user)):
    doc = await document_service.get_document(document_id, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: dict = Depends(get_current_active_user)):
    success = await document_service.delete_document(document_id, current_user)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found or already deleted")
    return {"message": f"Document '{document_id}' successfully deleted", "document_id": document_id}


@router.get("/{document_id}/download")
async def download_document(document_id: str, current_user: dict = Depends(get_current_active_user)):
    # Authorization happens BEFORE any storage access.
    doc = await document_service.get_document(document_id, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    resolved_path = None
    storage_key = doc.get("storage_key")
    if storage_key:
        resolved_path = storage_service.get_path(storage_key)
    if resolved_path is None:
        # Legacy documents stored an absolute path; confine it to the upload dir.
        resolved_path = resolve_within(UPLOAD_DIR, doc.get("file_path") or "")
    if not resolved_path or not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Original document file not found on storage")

    filename = Path(doc.get("filename") or resolved_path.name).name
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"
    return FileResponse(path=str(resolved_path), filename=filename, media_type=media_type)

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from fastapi.responses import FileResponse

from app.config import UPLOAD_DIR
from app.schemas.document import DocumentResponse, DocumentListResponse
from app.services.document_service import document_service, resolve_within
from app.utils.security import get_current_active_user, get_user_id

logger = logging.getLogger("docintel.documents")

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/process", response_model=DocumentResponse)
async def process_document(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    try:
        result = await document_service.process_document_file(
            file,
            current_user_email=current_user.get("email"),
            owner_id=get_user_id(current_user),
            organization_id=current_user.get("organization_id"),
        )
        return result
    except HTTPException:
        raise
    except Exception:
        logger.exception("Document processing pipeline failed.")
        raise HTTPException(status_code=500, detail="Document processing failed")


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
    # Authorization happens BEFORE any filesystem access.
    doc = await document_service.get_document(document_id, current_user)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Confine the resolved path to the upload directory (path traversal defence).
    resolved_path = resolve_within(UPLOAD_DIR, doc.get("file_path") or "")
    if not resolved_path or not resolved_path.exists() or not resolved_path.is_file():
        raise HTTPException(status_code=404, detail="Original document file not found on storage")

    filename = Path(doc.get("filename") or resolved_path.name).name
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"
    return FileResponse(path=str(resolved_path), filename=filename, media_type=media_type)

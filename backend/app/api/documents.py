import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from fastapi.responses import FileResponse

from app.schemas.document import DocumentResponse, DocumentListResponse
from app.services.document_service import document_service
from app.utils.security import get_current_user_optional, get_current_user

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/process", response_model=DocumentResponse)
async def process_document(
    file: UploadFile = File(...),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    user_email = current_user.get("email") if current_user else "anonymous"
    try:
        result = await document_service.process_document_file(file, current_user_email=user_email)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document processing failed: {str(e)}")


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    type: Optional[str] = Query(None, description="Filter by document type (Invoice, Contract, Identity, Form)"),
    status: Optional[str] = Query(None, description="Filter by status (Verified, Flagged)"),
    search: Optional[str] = Query(None, description="Search term for filename, document_id, or text"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    res = await document_service.list_documents(doc_type=type, status=status, search=search, page=page, limit=limit)
    return res


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str):
    doc = await document_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found")
    return doc


@router.delete("/{document_id}")
async def delete_document(document_id: str, current_user: dict = Depends(get_current_user)):
    success = await document_service.delete_document(document_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found or already deleted")
    return {"message": f"Document '{document_id}' successfully deleted", "document_id": document_id}


@router.get("/{document_id}/download")
async def download_document(document_id: str):
    doc = await document_service.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    file_path = doc.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Original document file not found on disk")

    filename = doc.get("filename", Path(file_path).name)
    media_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/png"
    return FileResponse(path=file_path, filename=filename, media_type=media_type)

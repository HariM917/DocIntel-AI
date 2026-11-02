from fastapi import APIRouter, HTTPException, Depends

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import rag_service
from app.services.document_service import document_service
from app.utils.security import get_current_active_user, get_user_id

router = APIRouter(prefix="/chat", tags=["AI Assistant"])


@router.post("", response_model=ChatResponse)
async def chat_with_documents(
    request: ChatRequest,
    current_user: dict = Depends(get_current_active_user),
):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="Chat message cannot be empty")

    # If a specific document is targeted, authorize it BEFORE retrieval.
    if request.document_id:
        doc = await document_service.get_document(request.document_id, current_user)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

    response_dict = await rag_service.answer_question(
        query=request.message.strip(),
        document_id=request.document_id,
        owner_id=get_user_id(current_user),
        owner_email=current_user.get("email"),
        organization_id=current_user.get("organization_id"),
    )
    return response_dict

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class SourceReference(BaseModel):
    document_id: str
    filename: str
    document_type: str
    snippet: str
    score: float


class ChatRequest(BaseModel):
    message: str
    document_id: Optional[str] = None  # Optional filter to a single document


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceReference] = []
    confidence: float = 0.9
    matched: bool = True

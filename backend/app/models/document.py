from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EntityModel(BaseModel):
    text: str
    type: str
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None


class PIIModel(BaseModel):
    type: str
    value: str
    masked_value: str
    confidence: float
    source: str = "regex"
    sensitive: bool = True
    valid: bool = True
    start: Optional[int] = None
    end: Optional[int] = None


class DocumentModel(BaseModel):
    id: Optional[str] = None
    document_id: str
    filename: str
    file_type: str
    file_size: int
    file_path: Optional[str] = None
    document_type: str
    classification_confidence: float
    status: str  # "Verified" | "Flagged" | "Pending"
    raw_text: str
    redacted_text: str
    entities: List[EntityModel] = []
    pii_entities: List[PIIModel] = []
    structured_data: Dict[str, Any] = {}
    confidence: float
    pipeline_steps: List[Dict[str, Any]] = []
    owner: str = "anonymous"
    created_at: str
    updated_at: str

    class Config:
        populate_by_name = True

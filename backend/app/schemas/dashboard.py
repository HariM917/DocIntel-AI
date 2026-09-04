from typing import Dict, List, Optional
from pydantic import BaseModel


class RecentDocumentItem(BaseModel):
    document_id: str
    filename: str
    document_type: str
    extracted_vendor_or_name: str
    created_at: str
    status: str
    confidence: float


class DashboardStats(BaseModel):
    total_processed: int
    extraction_accuracy: float
    protected_entities: int
    time_saved: str
    type_distribution: Dict[str, int]
    status_distribution: Dict[str, int]
    recent_documents: List[RecentDocumentItem]

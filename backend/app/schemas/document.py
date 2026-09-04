from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EntityItem(BaseModel):
    text: str
    type: str  # PERSON, ORGANIZATION, LOCATION, DATE, MONEY, etc.
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None


class PIIEntityItem(BaseModel):
    type: str  # AADHAAR, PAN, EMAIL, PHONE, BANK_ACCOUNT, CREDIT_CARD, etc.
    value: str
    masked_value: str
    confidence: float
    source: str = "regex"  # "roberta" | "regex" | "rule"
    sensitive: bool = True
    valid: bool = True
    start: Optional[int] = None
    end: Optional[int] = None


class StructuredInvoice(BaseModel):
    invoice_number: Optional[str] = "N/A"
    invoice_date: Optional[str] = "N/A"
    due_date: Optional[str] = "N/A"
    vendor_name: Optional[str] = "N/A"
    customer_name: Optional[str] = "N/A"
    subtotal: Optional[str] = "N/A"
    tax: Optional[str] = "N/A"
    total_amount: Optional[str] = "N/A"
    currency: Optional[str] = "INR"


class StructuredContract(BaseModel):
    contract_number: Optional[str] = "N/A"
    parties: List[str] = []
    effective_date: Optional[str] = "N/A"
    expiry_date: Optional[str] = "N/A"
    governing_law: Optional[str] = "N/A"


class StructuredIdentity(BaseModel):
    name: Optional[str] = "N/A"
    document_type: Optional[str] = "N/A"
    document_number: Optional[str] = "N/A"
    date_of_birth: Optional[str] = "N/A"
    gender: Optional[str] = "N/A"
    address: Optional[str] = "N/A"


class StructuredForm(BaseModel):
    applicant_name: Optional[str] = "N/A"
    email: Optional[str] = "N/A"
    phone: Optional[str] = "N/A"
    dates: List[str] = []
    relevant_fields: Dict[str, Any] = {}


class PipelineStep(BaseModel):
    name: str
    status: str = "completed"  # pending, in_progress, completed, failed
    duration_ms: float = 0.0
    details: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    document_id: str
    filename: str
    file_type: str
    file_size: int
    document_type: str
    classification_confidence: float
    status: str  # Verified, Flagged, Pending
    raw_text: str
    redacted_text: str
    entities: List[EntityItem] = []
    pii_entities: List[PIIEntityItem] = []
    structured_data: Dict[str, Any] = {}
    confidence: float
    pipeline_steps: List[PipelineStep] = []
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    limit: int

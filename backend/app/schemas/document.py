from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EntityItem(BaseModel):
    text: str
    type: str  # PERSON, ORGANIZATION, LOCATION, DATE, MONEY, etc.
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None
    # Phase 3 — additive provenance/handling fields (never replace `text`).
    label: Optional[str] = None
    source: Optional[str] = None          # "roberta" | "rule"
    confidence_source: Optional[str] = None  # "model" | "heuristic"
    calibrated: Optional[bool] = None
    normalized_value: Optional[str] = None


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
    document_type: str = "Other"
    classification_confidence: float = 0.0
    status: str = "Pending"  # Verified, Flagged, Pending
    # Asynchronous processing lifecycle
    processing_status: str = "completed"
    processing_error: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    raw_text: str = ""
    redacted_text: str = ""
    entities: List[EntityItem] = []
    pii_entities: List[PIIEntityItem] = []
    structured_data: Dict[str, Any] = {}
    # Per-field provenance/confidence metadata (Step 11/24): value, confidence
    # (None when not computable), source and validation verdict.
    structured_fields: Dict[str, Any] = {}
    confidence: float = 0.0
    pipeline_steps: List[PipelineStep] = []
    # Phase 3 — additive, safe processing metadata (Step 25/35).
    # `raw_text`/`structured_data` retain their original Phase 1/2 meaning.
    normalized_text: str = ""
    structure: Dict[str, Any] = {}
    quality: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    processing_metrics: Dict[str, Any] = {}
    stage_metadata: Optional[Dict[str, Any]] = None
    processing_warnings: List[str] = []
    pipeline_version: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class DocumentListResponse(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    limit: int


class DocumentUploadResponse(BaseModel):
    """Returned immediately after an upload is accepted for processing."""

    document_id: str
    job_id: str
    status: str = "queued"


class ProcessingErrorInfo(BaseModel):
    code: str
    message: str


class DocumentStatusResponse(BaseModel):
    """Safe, authorization-scoped view of a document's processing state."""

    document_id: str
    status: str  # uploaded | queued | processing | completed | failed | cancelled
    validation_status: Optional[str] = None  # Verified | Flagged | Pending
    progress: Optional[int] = None
    attempts: int = 0
    error: Optional[ProcessingErrorInfo] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

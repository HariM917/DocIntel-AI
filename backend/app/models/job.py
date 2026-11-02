from typing import Optional
from pydantic import BaseModel


class ProcessingJobModel(BaseModel):
    """Tracks the lifecycle of an asynchronous document processing job.

    A job only *references* its document; it never duplicates document content.
    """

    id: Optional[str] = None
    job_id: str
    document_id: str
    owner_id: Optional[str] = None
    organization_id: Optional[str] = None
    # queued | processing | completed | failed | cancelled
    status: str = "queued"
    attempts: int = 0
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    failed_at: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

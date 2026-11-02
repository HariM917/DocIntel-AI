"""Canonical pipeline stage model (Phase 3, Step 2).

The intelligence pipeline is described as an ordered set of named stages. Each
stage records *safe* processing metadata (never document content, PII or stack
traces):

    current_stage, stage_started_at, stage_completed_at, stage_error

Every stage also carries a ``critical`` flag used by the failure strategy
(Step 16): a critical stage failure aborts the document, whereas a non-critical
failure is recorded as a warning and the pipeline continues.
"""
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("docintel.pipeline")

# Ordered stages. Not every stage is exposed publicly; the worker only needs to
# know which stage failed.
UPLOAD = "UPLOAD"
OCR = "OCR"
TEXT_NORMALIZATION = "TEXT_NORMALIZATION"
STRUCTURE_ANALYSIS = "STRUCTURE_ANALYSIS"
ENTITY_EXTRACTION = "ENTITY_EXTRACTION"
PII_DETECTION = "PII_DETECTION"
REDACTION = "REDACTION"
STRUCTURED_EXTRACTION = "STRUCTURED_EXTRACTION"
VALIDATION = "VALIDATION"
QUALITY_ASSESSMENT = "QUALITY_ASSESSMENT"
EMBEDDING = "EMBEDDING"
INDEXING = "INDEXING"
COMPLETED = "COMPLETED"

# Stages whose failure destroys the whole document. A document cannot be
# usefully processed if its text could not be read at all.
CRITICAL_STAGES = {UPLOAD, OCR}

_STAGE_ORDER = [
    OCR,
    TEXT_NORMALIZATION,
    STRUCTURE_ANALYSIS,
    ENTITY_EXTRACTION,
    PII_DETECTION,
    REDACTION,
    STRUCTURED_EXTRACTION,
    VALIDATION,
    QUALITY_ASSESSMENT,
    EMBEDDING,
    INDEXING,
]


def _now() -> str:
    return datetime.utcnow().isoformat()


class StageTracker:
    """Records per-stage timing/status metadata for a single pipeline run.

    Only operational metadata is retained. Error strings are short, classified
    codes/messages supplied by the caller -- never raw exception text.
    """

    def __init__(self) -> None:
        self.records: List[Dict[str, Any]] = []
        self.current_stage: Optional[str] = None

    def start(self, stage: str) -> float:
        self.current_stage = stage
        return time.perf_counter()

    def complete(self, stage: str, started: float, status: str = "completed",
                 error: Optional[str] = None) -> Dict[str, Any]:
        record = {
            "stage": stage,
            "status": status,
            "started_at": None,
            "completed_at": _now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": error,
        }
        self.records.append(record)
        if self.current_stage == stage:
            self.current_stage = None
        return record

    @property
    def summary(self) -> Dict[str, Any]:
        return {
            "current_stage": self.current_stage,
            "stages": self.records,
        }


def is_critical(stage: str) -> bool:
    return stage in CRITICAL_STAGES

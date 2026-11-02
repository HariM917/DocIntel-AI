"""Phase 3 — document intelligence / AI pipeline tests.

Covers the Phase 3 acceptance surface: the pipeline stage model, OCR quality
handling, text normalization (with header/footer safety), structure detection,
entity enrichment, PII/redaction robustness, field & cross-field validation,
quality scoring, semantic chunking, resource limits, and the staged pipeline
driver itself.

The heavy OCR/NER components are monkeypatched where determinism (not model
behaviour) is under test; the model-specific unit tests live in test_ocr.py and
test_ner.py.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import settings
from app.services import processing_service
from app.services.embedding_service import embedding_service
from app.services.ner_service import ner_service
from app.services.pii_service import pii_service
from app.services.pipeline_stages import StageTracker, OCR, VALIDATION, is_critical
from app.services.quality_service import quality_service, quality_level
from app.services.redaction_service import redaction_service
from app.services.structure_service import structure_service
from app.services.structured_extraction import structured_extraction_service
from app.services.text_normalization_service import PAGE_BREAK, text_normalization_service
from app.services.validation_service import validation_service

from tests.phase3_samples import CATEGORIES, SAMPLES


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
CRAFTED_TEXT = (
    "INVOICE\n"
    "Vendor: Acme Corp\n"
    "Invoice No: INV-1001\n"
    "Invoice Date: 15/01/2024\n"
    "Due Date: 30/01/2024\n"
    "Subtotal: 1000.00\n"
    "Tax: 180.00\n"
    "Total Amount: 1180.00\n"
    "Email: jane.doe@example.com\n"
    "Phone: 9876543210\n"
    "PAN: ABCDE1234F\n"
    "Aadhaar: 4321 8765 2109\n"
)


def _fake_ocr(text: str, confidence: float = 0.9, pages: int = 1):
    def _fn(_file_path):
        return {
            "text": text,
            "confidence": confidence,
            "pages": pages,
            "method": "test",
            "empty": not bool(text.strip()),
            "warnings": [] if text.strip() else ["OCR produced no usable text."],
        }
    return _fn


def _fake_entities(_text: str):
    return [{
        "text": "Acme Corp",
        "type": "ORGANIZATION",
        "confidence": 0.9,
        "start": 0,
        "end": 9,
        "label": "ORGANIZATION",
        "source": "rule",
        "confidence_source": "heuristic",
        "calibrated": False,
        "normalized_value": "Acme Corp",
    }]


def _png_bytes() -> io.BytesIO:
    img = Image.new("RGB", (200, 150), color=(250, 250, 250))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Step 2 — pipeline stage model
# ---------------------------------------------------------------------------
def test_stage_tracker_records_safe_metadata():
    tracker = StageTracker()
    started = tracker.start(OCR)
    assert tracker.current_stage == OCR
    record = tracker.complete(OCR, started, status="completed")
    assert record["stage"] == OCR
    assert record["status"] == "completed"
    assert record["duration_ms"] >= 0
    assert record["error"] is None
    assert tracker.current_stage is None
    summary = tracker.summary
    assert summary["current_stage"] is None
    assert len(summary["stages"]) == 1


def test_critical_stage_classification():
    assert is_critical(OCR) is True
    assert is_critical(VALIDATION) is False


# ---------------------------------------------------------------------------
# Steps 3 & 4 — OCR quality + text normalization
# ---------------------------------------------------------------------------
def test_normalization_preserves_semantically_important_tokens():
    raw = "Email: a@b.com  Phone: 9876543210  Amount: 1,180.00\n\n\n\nSecond   paragraph"
    res = text_normalization_service.normalize(raw)
    nt = res["normalized_text"]
    assert "a@b.com" in nt
    assert "9876543210" in nt
    assert "1,180.00" in nt
    assert res["original_text"] == raw          # original OCR text preserved
    assert "\n\n\n\n" not in nt                  # excessive blank lines collapsed
    assert res["empty"] is False


def test_normalization_flags_empty_text():
    res = text_normalization_service.normalize("   \n  ")
    assert res["empty"] is True
    assert res["normalized_text"] == ""
    assert res["warnings"]


def test_normalization_removes_only_repeated_headers_not_content():
    raw = (
        "COMPANY HEADER\nfirst page body"
        f"{PAGE_BREAK}COMPANY HEADER\nsecond page body"
        f"{PAGE_BREAK}COMPANY HEADER\nthird page body"
    )
    res = text_normalization_service.normalize(raw)
    nt = res["normalized_text"]
    assert nt.count("COMPANY HEADER") == 1       # later duplicates removed
    assert "second page body" in nt              # unique content is preserved
    assert "third page body" in nt


# ---------------------------------------------------------------------------
# Step 5 — document structure detection
# ---------------------------------------------------------------------------
def test_structure_detection_finds_headings_and_key_values():
    text = "INVOICE\nVendor: Acme Corp\nCustomer: Jane Doe\n\n- item one\n- item two"
    structure = structure_service.analyze(text)
    assert structure["key_value_fields"].get("Vendor") == "Acme Corp"
    assert any(h["text"] == "INVOICE" for h in structure["headings"])
    assert structure["paragraph_count"] >= 1


# ---------------------------------------------------------------------------
# Step 7/24 — entity enrichment
# ---------------------------------------------------------------------------
def test_ner_enrichment_provides_provenance_fields():
    entities = ner_service._enrich(
        [{"text": "Acme Corp", "type": "ORGANIZATION", "confidence": 0.9, "start": 0, "end": 9}],
        source="rule",
        calibrated=False,
    )
    ent = entities[0]
    assert ent["text"] == "Acme Corp"            # original text untouched
    assert ent["label"] == "ORGANIZATION"
    assert ent["source"] == "rule"
    assert ent["confidence_source"] == "heuristic"
    assert ent["calibrated"] is False
    assert "normalized_value" in ent


# ---------------------------------------------------------------------------
# Step 8 — PII detection output shape
# ---------------------------------------------------------------------------
def test_pii_detection_has_required_fields():
    detected = pii_service.detect_pii("Email: a@b.com Phone: 9876543210")
    assert detected
    for item in detected:
        for key in ("type", "value", "start", "end", "confidence", "source"):
            assert key in item


# ---------------------------------------------------------------------------
# Step 9 — redaction robustness
# ---------------------------------------------------------------------------
def test_redaction_handles_repeated_and_adjacent_pii():
    text = "a@b.com a@b.com 9876543210 b@c.com"
    pii = pii_service.detect_pii(text)
    redacted, _ = redaction_service.redact_document(text, pii)
    assert "a@b.com" not in redacted
    assert "b@c.com" not in redacted
    assert "9876543210" not in redacted


def test_redaction_overlapping_and_unicode_pii():
    text = "Contact jane@example.com now. Employee: José Alvarez"
    pii = pii_service.detect_pii(text)
    pii.append({
        "type": "PERSON", "value": "José Alvarez", "confidence": 0.9,
        "source": "roberta", "sensitive": True, "valid": True, "start": 0, "end": 12,
    })
    redacted, _ = redaction_service.redact_document(text, pii, {"PERSON": True})
    assert "jane@example.com" not in redacted
    assert "José Alvarez" not in redacted


# ---------------------------------------------------------------------------
# Steps 12 & 13 — field and cross-field validation
# ---------------------------------------------------------------------------
def test_validate_date_rejects_impossible_values():
    assert validation_service.validate_date("15/01/2024")[0] is True
    assert validation_service.validate_date("99/99/9999")[0] is False


def test_validate_url_currency_numeric_identifier():
    assert validation_service.validate_url("https://example.com/path")[0] is True
    assert validation_service.validate_url("not a url")[0] is False
    assert validation_service.validate_currency("₹1,180.00")[0] is True
    assert validation_service.validate_numeric("1,234.56")[0] is True
    assert validation_service.validate_identifier("INV-1001")[0] is True


def test_classify_field_valid_invalid_uncertain():
    assert validation_service.classify_field("email", "a@b.com") == "valid"
    assert validation_service.classify_field("email", "not-an-email") == "invalid"
    assert validation_service.classify_field("mystery_field", "x") == "uncertain"
    # Compound schema names resolve by token.
    assert validation_service.classify_field("invoice_date", "15/01/2024") == "valid"
    assert validation_service.classify_field("total_amount", "₹1,180.00") == "valid"


def test_cross_field_invoice_total_consistency():
    bad = validation_service.cross_field_validate(
        "Invoice", {"subtotal": "1000.00", "tax": "180.00", "total_amount": "2000.00"}
    )
    assert any(w["code"] == "CROSS_FIELD_MISMATCH" for w in bad)
    good = validation_service.cross_field_validate(
        "Invoice", {"subtotal": "1000.00", "tax": "180.00", "total_amount": "1180.00"}
    )
    assert good == []


# ---------------------------------------------------------------------------
# Steps 14 & 15 — quality scoring
# ---------------------------------------------------------------------------
def test_quality_levels_and_score_bounds():
    assert quality_level(0.95) == "excellent"
    assert quality_level(0.80) == "good"
    assert quality_level(0.60) == "fair"
    assert quality_level(0.20) == "poor"

    result = quality_service.assess(
        ocr_confidence=0.95, text_length=1000, entity_count=6,
        structured_data={"a": "x", "b": "y"}, validation_failures=0,
    )
    assert 0.0 <= result["score"] <= 1.0
    assert result["level"] in {"excellent", "good", "fair", "poor"}


def test_quality_poor_when_no_text():
    result = quality_service.assess(
        ocr_confidence=0.0, text_length=0, entity_count=0,
        structured_data={}, validation_failures=0, ocr_empty=True,
    )
    assert result["score"] == 0.0
    assert result["level"] == "poor"


# ---------------------------------------------------------------------------
# Steps 19 & 26 — semantic chunking quality
# ---------------------------------------------------------------------------
def test_chunking_skips_page_breaks_and_tiny_chunks():
    text = (
        "Section One\n\n" + ("real content sentence. " * 5)
        + f"{PAGE_BREAK}Section Two\n\n" + ("more content here. " * 5)
        + "\n\nhi"
    )
    chunks = embedding_service.chunk_text(text, chunk_size=400)
    assert chunks
    assert all("--- Page Break ---" not in c["text"] for c in chunks)
    assert all(len(c["text"].strip()) >= settings.MIN_CHUNK_CHARS for c in chunks)
    assert all(c["text"].strip() != "hi" for c in chunks)


# ---------------------------------------------------------------------------
# Steps 2-24 — staged pipeline driver
# ---------------------------------------------------------------------------
def test_staged_pipeline_produces_phase3_metadata(monkeypatch):
    monkeypatch.setattr(processing_service.ocr_service, "process_document", _fake_ocr(CRAFTED_TEXT))
    monkeypatch.setattr(processing_service.ner_service, "extract_entities", _fake_entities)

    result = processing_service._run_pipeline_sync(
        Path("dummy.png"), "dummy.png", ".png",
        {"EMAIL": True, "PHONE": True, "AADHAAR": True, "PAN": True,
         "CREDIT_CARD": True, "BANK_ACCOUNT": True},
    )

    # Phase 1/2 keys remain present.
    for key in ("document_type", "status", "confidence", "raw_text",
                "redacted_text", "entities", "pii_entities", "structured_data",
                "pipeline_steps"):
        assert key in result

    # Phase 3 additive keys.
    assert result["pipeline_version"] == settings.PIPELINE_VERSION
    assert result["raw_text"] == CRAFTED_TEXT              # original OCR preserved
    assert result["normalized_text"]
    assert result["quality"]["level"] in {"excellent", "good", "fair", "poor"}
    assert "fields" in result["validation"]

    # All canonical stages executed and were timed.
    for stage in ("OCR", "TEXT_NORMALIZATION", "STRUCTURE_ANALYSIS",
                  "ENTITY_EXTRACTION", "PII_DETECTION", "REDACTION",
                  "STRUCTURED_EXTRACTION", "VALIDATION", "QUALITY_ASSESSMENT"):
        assert stage in result["processing_metrics"]
        assert any(s["stage"] == stage for s in result["stage_metadata"]["stages"])

    # Sensitive values are redacted in the derived text.
    assert "jane.doe@example.com" not in result["redacted_text"]
    assert "9876543210" not in result["redacted_text"]


def test_pipeline_detects_empty_ocr_as_degraded(monkeypatch):
    monkeypatch.setattr(processing_service.ocr_service, "process_document", _fake_ocr(""))
    monkeypatch.setattr(processing_service.ner_service, "extract_entities", lambda _t: [])

    result = processing_service._run_pipeline_sync(
        Path("dummy.png"), "dummy.png", ".png", {}
    )
    assert result["quality"]["level"] == "poor"
    assert result["quality"]["score"] < 0.5
    assert any("usable text" in issue.lower() for issue in result["quality"]["issues"])
    assert any("no usable text" in w.lower() for w in result["processing_warnings"])
    assert any(s["stage"] == "OCR" and s["status"] == "warning"
               for s in result["stage_metadata"]["stages"])


def test_pipeline_enforces_max_text_length(monkeypatch):
    monkeypatch.setattr(processing_service.ocr_service, "process_document",
                        _fake_ocr("X" * 500))
    monkeypatch.setattr(processing_service.ner_service, "extract_entities", lambda _t: [])
    monkeypatch.setattr(processing_service.settings, "MAX_TEXT_LENGTH", 100)

    result = processing_service._run_pipeline_sync(
        Path("dummy.png"), "dummy.png", ".png", {}
    )
    assert len(result["normalized_text"]) <= 100
    assert any("MAX_TEXT_LENGTH" in w for w in result["processing_warnings"])


# ---------------------------------------------------------------------------
# Steps 25/34/35 — API compatibility & document detail response
# ---------------------------------------------------------------------------
def test_document_detail_exposes_phase3_metadata(client: TestClient, auth_headers):
    headers, _ = auth_headers("phase3_detail")
    res = client.post(
        "/api/documents/process",
        headers=headers,
        files={"file": ("doc.png", _png_bytes(), "image/png")},
    )
    assert res.status_code == 202
    doc_id = res.json()["document_id"]

    doc = client.get(f"/api/documents/{doc_id}", headers=headers).json()
    assert doc["processing_status"] == "completed"
    # Additive Phase 3 fields are exposed without breaking the Phase 1/2 shape.
    assert doc["pipeline_version"] == settings.PIPELINE_VERSION
    assert doc["quality"] is not None
    assert "level" in doc["quality"]
    assert isinstance(doc["processing_metrics"], dict)
    assert doc["stage_metadata"] is not None
    assert "raw_text" in doc and "structured_data" in doc


# ---------------------------------------------------------------------------
# Steps 10/11/24 — schema-driven extraction with per-field provenance
# ---------------------------------------------------------------------------
def test_extraction_reports_field_provenance_and_confidence():
    entities = [{
        "text": "Acme Corp", "type": "ORGANIZATION", "confidence": 0.82,
        "start": 0, "end": 9,
    }]
    text = (
        "INVOICE\n"
        "Invoice No: INV-1001\n"
        "Invoice Date: 15/01/2024\n"
        "Subtotal: 1000.00\n"
        "Tax: 180.00\n"
        "Total Amount: 1180.00\n"
    )
    result = structured_extraction_service.extract_with_metadata("Invoice", text, entities, [])
    meta = result["field_metadata"]

    # Flat data shape is unchanged (backward compatible).
    assert result["structured_data"]["invoice_number"] == "INV-1001"

    # Rule-anchored fields carry a documented, non-null confidence.
    assert meta["invoice_number"]["source"] == "rule"
    assert meta["invoice_number"]["confidence"] == 0.9

    # Entity-derived field inherits the entity's own confidence (not invented).
    assert meta["vendor_name"]["source"] == "ner"
    assert meta["vendor_name"]["confidence"] == 0.82

    # Absent field -> confidence is null, source is honestly "not_found".
    assert meta["due_date"]["confidence"] is None
    assert meta["due_date"]["source"] == "not_found"


def test_pipeline_exposes_structured_fields(monkeypatch):
    monkeypatch.setattr(processing_service.ocr_service, "process_document", _fake_ocr(CRAFTED_TEXT))
    monkeypatch.setattr(processing_service.ner_service, "extract_entities", _fake_entities)

    result = processing_service._run_pipeline_sync(Path("dummy.png"), "dummy.png", ".png", {})
    fields = result["structured_fields"]
    assert fields
    for entry in fields.values():
        assert set(entry) >= {"value", "confidence", "source"}
    # Validation verdicts are merged into the per-field metadata.
    assert "validated" in fields["total_amount"]
    assert fields["total_amount"]["validated"] in {"valid", "invalid", "uncertain"}


# ---------------------------------------------------------------------------
# Step 9 — deterministic placeholder redaction mode
# ---------------------------------------------------------------------------
def test_placeholder_redaction_mode_is_deterministic(monkeypatch):
    monkeypatch.setattr(settings, "PII_REDACTION_MODE", "placeholder")
    text = "Email: jane@example.com Phone: 9876543210"
    pii = pii_service.detect_pii(text)
    redacted, _ = redaction_service.redact_document(text, pii)
    assert "[REDACTED_EMAIL]" in redacted
    assert "[REDACTED_PHONE]" in redacted
    assert "jane@example.com" not in redacted
    assert "9876543210" not in redacted


# ---------------------------------------------------------------------------
# Steps 27 & 28 — ten-category fixtures run cleanly end-to-end
# ---------------------------------------------------------------------------
def test_ten_category_fixtures_present():
    assert len(SAMPLES) == 10
    assert len(set(CATEGORIES)) == 10


@pytest.mark.parametrize("category,text", SAMPLES)
def test_each_category_processes_without_crashing(monkeypatch, category, text):
    monkeypatch.setattr(processing_service.ocr_service, "process_document", _fake_ocr(text))
    monkeypatch.setattr(processing_service.ner_service, "extract_entities", _fake_entities)

    result = processing_service._run_pipeline_sync(Path("dummy.png"), "dummy.png", ".png",
                                                   {"EMAIL": True, "PHONE": True})
    assert result["normalized_text"]
    assert result["quality"]["level"] in {"excellent", "good", "fair", "poor"}
    assert isinstance(result["structured_data"], dict)
    assert isinstance(result["structured_fields"], dict)
    # Sensitive values detected in the fixture are removed from the derived text.
    for item in result["pii_entities"]:
        if item.get("sensitive"):
            assert item["value"] not in result["redacted_text"]

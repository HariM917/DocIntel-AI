import os
from pathlib import Path
import pytest
from PIL import Image

from app.services.ocr_service import ocr_service
from app.config import SAMPLE_DOCS_DIR


def test_ocr_image_preprocessing():
    # Create simple in-memory image
    img = Image.new("RGB", (200, 100), color=(255, 255, 255))
    preprocessed = ocr_service.preprocess_image(img)
    assert preprocessed is not None
    assert preprocessed.size == (200, 100)


def test_ocr_pdf_extraction():
    sample_pdf = SAMPLE_DOCS_DIR / "sample_invoice.pdf"
    if sample_pdf.exists():
        result = ocr_service.process_document(sample_pdf)
        assert result["text"] != ""
        assert result["confidence"] > 0.5
        assert result["pages"] >= 1
        assert any(term in result["text"].upper() for term in ["INVOICE", "INVEICE", "CLOUD", "TOTAL", "INR"])


def test_ocr_unsupported_extension():
    with pytest.raises(ValueError):
        ocr_service.process_document(Path("test.docx"))

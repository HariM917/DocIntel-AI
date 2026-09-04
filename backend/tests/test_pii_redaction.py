import pytest
from app.services.pii_service import pii_service
from app.services.validation_service import validation_service
from app.services.redaction_service import redaction_service


def test_validation_aadhaar():
    # Valid format: 12 digits, doesn't start with 0 or 1
    valid, msg = validation_service.validate_aadhaar("9876 5432 1098")
    assert valid is True

    # Invalid: Starts with 0
    invalid1, msg1 = validation_service.validate_aadhaar("0123 4567 8901")
    assert invalid1 is False

    # Invalid length
    invalid2, msg2 = validation_service.validate_aadhaar("12345")
    assert invalid2 is False


def test_validation_pan():
    # Valid PAN format: 5 uppercase letters, 4 digits, 1 letter (4th char is taxpayer type, e.g. P for Person, C for Company)
    valid, msg = validation_service.validate_pan("ABCDE1234F")
    assert valid is True

    # Invalid format
    invalid, msg = validation_service.validate_pan("12345ABCDE")
    assert invalid is False


def test_validation_luhn():
    # Standard valid Visa test card
    assert validation_service.validate_luhn("4532015112830366") is True
    # Invalid card number
    assert validation_service.validate_luhn("4532015112830367") is False


def test_pii_detection():
    sample_text = (
        "Customer Name: Rahul Verma\n"
        "Email: rahul.verma@example.com\n"
        "Phone: +91 9876543210\n"
        "Aadhaar Number: 9876 5432 1098\n"
        "PAN Card: ABCDE1234F\n"
        "Bank Account: 123456789012\n"
    )

    detected = pii_service.detect_pii(sample_text)
    types_detected = {p["type"] for p in detected}

    assert "EMAIL" in types_detected
    assert "PHONE" in types_detected
    assert "AADHAAR" in types_detected
    assert "PAN" in types_detected
    assert "BANK_ACCOUNT" in types_detected


def test_redaction_masking():
    # Email masking: rahul.verma@example.com -> r***a@example.com
    masked_email = redaction_service.mask_email("rahul@example.com")
    assert "rahul@example.com" not in masked_email
    assert "@example.com" in masked_email
    assert masked_email.startswith("r***")

    # Aadhaar masking: 9876 5432 1098 -> XXXX XXXX 1098
    masked_aadhaar = redaction_service.mask_aadhaar("9876 5432 1098")
    assert masked_aadhaar == "XXXX XXXX 1098"

    # PAN masking: ABCDE1234F -> XXXXX1234F
    masked_pan = redaction_service.mask_pan("ABCDE1234F")
    assert masked_pan == "XXXXX1234F"

    # Phone masking: 9876543210 -> ******3210
    masked_phone = redaction_service.mask_phone("9876543210")
    assert masked_phone.endswith("3210")
    assert "987654" not in masked_phone


def test_full_document_redaction():
    text = "User contact is rahul@example.com with PAN ABCDE1234F and phone 9876543210."
    pii_entities = pii_service.detect_pii(text)
    redacted_text, processed_entities = redaction_service.redact_document(text, pii_entities)

    assert "rahul@example.com" not in redacted_text
    assert "ABCDE1234F" not in redacted_text
    assert "XXXXX1234F" in redacted_text

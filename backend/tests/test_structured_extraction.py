import pytest
from app.services.document_classifier import document_classifier
from app.services.structured_extraction import structured_extraction_service


def test_document_classification():
    # Invoice text
    invoice_text = "TAX INVOICE Invoice No: INV-2025-01 Billed To: Acme Corp Total Amount: $4,500.00 Due Date: 2025-02-15"
    inv_class = document_classifier.classify(invoice_text)
    assert inv_class["document_type"] == "Invoice"
    assert inv_class["confidence"] > 0.6

    # Contract text
    contract_text = "MASTER SERVICES AGREEMENT by and between Alpha Corp and Beta LLC. NOW, THEREFORE, the parties agree..."
    cont_class = document_classifier.classify(contract_text)
    assert cont_class["document_type"] == "Contract"

    # Identity text
    id_text = "GOVERNMENT OF INDIA UNIQUE IDENTIFICATION AUTHORITY AADHAAR 9876 5432 1098 DOB: 12/04/1992 Male"
    id_class = document_classifier.classify(id_text)
    assert id_class["document_type"] == "Identity"


def test_structured_invoice_extraction():
    text = (
        "TAX INVOICE\n"
        "Invoice No: INV-9014\n"
        "Invoice Date: 15/01/2025\n"
        "Due Date: 30/01/2025\n"
        "Vendor: Tech Innovations Ltd\n"
        "Customer: Apex Global\n"
        "Subtotal: $4,000.00\n"
        "Tax: $500.00\n"
        "Total Amount: $4,500.00\n"
    )
    entities = [
        {"text": "Tech Innovations Ltd", "type": "ORGANIZATION", "confidence": 0.95},
        {"text": "Apex Global", "type": "ORGANIZATION", "confidence": 0.92},
    ]
    pii_entities = [
        {"type": "INVOICE_NUMBER", "value": "INV-9014"},
        {"type": "DATE", "value": "15/01/2025"},
        {"type": "DATE", "value": "30/01/2025"},
    ]

    structured = structured_extraction_service.extract("Invoice", text, entities, pii_entities)

    assert structured["invoice_number"] == "INV-9014"
    assert structured["total_amount"] == "4,500.00"
    assert structured["currency"] == "USD"
    assert structured["vendor_name"] != "N/A"


def test_structured_contract_extraction():
    text = (
        "EMPLOYMENT AGREEMENT\n"
        "Agreement No: AGR-2025-09\n"
        "Effective Date: 01/02/2025\n"
        "Governing Law: laws of the State of California.\n"
    )
    entities = [
        {"text": "Acme Corp", "type": "ORGANIZATION", "confidence": 0.95},
        {"text": "John Doe", "type": "PERSON", "confidence": 0.94},
    ]
    pii_entities = [
        {"type": "DATE", "value": "01/02/2025"},
    ]

    structured = structured_extraction_service.extract("Contract", text, entities, pii_entities)

    assert structured["contract_number"] == "AGR-2025-09"
    assert structured["effective_date"] == "01/02/2025"
    assert "Acme Corp" in structured["parties"]
    assert "John Doe" in structured["parties"]


def test_no_hallucination_on_missing_fields():
    sparse_text = "Generic text with no monetary amounts or dates."
    structured = structured_extraction_service.extract("Invoice", sparse_text, [], [])
    assert structured["total_amount"] == "N/A"
    assert structured["invoice_number"] == "N/A"

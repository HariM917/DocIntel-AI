"""Phase 3 test fixtures (Step 27) — sample documents across ten categories.

Each fixture is deliberately synthetic (no real PII). The samples exercise the
intelligence pipeline end-to-end: OCR text -> normalization -> structure ->
entity/PII extraction -> structured extraction -> validation -> quality.

``SAMPLES`` is a list of ``(category, text)`` pairs. It is intentionally a plain
data module (not a ``test_*`` file) so it can be reused by any test.
"""

SAMPLES = [
    (
        "invoice",
        "INVOICE\n"
        "Vendor: Acme Corp\n"
        "Bill To: Jane Doe\n"
        "Invoice No: INV-1001\n"
        "Invoice Date: 15/01/2024\n"
        "Due Date: 30/01/2024\n"
        "Subtotal: 1000.00\n"
        "Tax: 180.00\n"
        "Total Amount: 1180.00\n"
        "Email: jane.doe@example.com\n"
        "Phone: 9876543210\n",
    ),
    (
        "receipt",
        "SUPERMARKET RECEIPT\n"
        "Date: 02/02/2024\n"
        "Item Total: 450.00\n"
        "Tax: 22.50\n"
        "Grand Total: 472.50\n"
        "Card: 4532015112830366\n",
    ),
    (
        "resume",
        "RESUME\n"
        "Name: Rahul Verma\n"
        "Email: rahul.verma@example.com\n"
        "Phone: +91 9876543210\n"
        "Address: 12 MG Road, Bengaluru\n"
        "Experience: 6 years\n",
    ),
    (
        "identity",
        "GOVERNMENT IDENTITY CARD\n"
        "Name: Sita Devi\n"
        "Date of Birth: 04/09/1990\n"
        "Gender: Female\n"
        "Aadhaar: 4321 8765 2109\n"
        "PAN: ABCDE1234F\n",
    ),
    (
        "contract",
        "SERVICE AGREEMENT\n"
        "Contract No: CTR-7788\n"
        "Effective Date: 01/03/2024\n"
        "Expiry Date: 28/02/2025\n"
        "Parties: Acme Corp and Globex Ltd\n"
        "This agreement is governed by the laws of India.\n",
    ),
    (
        "bank_statement",
        "BANK STATEMENT\n"
        "Account Number: 123456789012\n"
        "Statement Date: 31/01/2024\n"
        "Opening Balance: 5000.00\n"
        "Closing Balance: 7200.00\n"
        "Email: support@examplebank.com\n",
    ),
    (
        "purchase_order",
        "PURCHASE ORDER\n"
        "PO Number: PO-5566\n"
        "Order Date: 10/02/2024\n"
        "Supplier: Globex Ltd\n"
        "Total Amount: 25000.00\n"
        "Currency: INR\n",
    ),
    (
        "medical_report",
        "MEDICAL REPORT\n"
        "Patient Name: Anita Rao\n"
        "Date of Birth: 12/12/1985\n"
        "Phone: 9812345678\n"
        "Diagnosis: Seasonal allergy\n"
        "Follow-up Date: 20/03/2024\n",
    ),
    (
        "utility_bill",
        "ELECTRICITY BILL\n"
        "Consumer No: 9988776655\n"
        "Bill Date: 05/02/2024\n"
        "Due Date: 25/02/2024\n"
        "Amount Payable: 1875.50\n"
        "Email: customer@powerco.example\n",
    ),
    (
        "general",
        "MEETING NOTES\n"
        "Attendees: John Smith, Maria Garcia\n"
        "Organizations: Acme Corp, Globex Ltd\n"
        "Location: Bengaluru\n"
        "Next review scheduled for 15/04/2024.\n",
    ),
]

CATEGORIES = [category for category, _ in SAMPLES]

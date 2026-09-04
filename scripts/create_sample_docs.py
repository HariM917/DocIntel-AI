import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import fitz

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BASE_DIR / "data" / "sample_documents"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)


def create_invoice():
    # 1. Invoice PDF and Image
    pdf_path = SAMPLE_DIR / "sample_invoice.pdf"
    png_path = SAMPLE_DIR / "sample_invoice.png"

    # Create high-res PIL Image
    width, height = 1200, 1600
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Title & Header
    draw.rectangle([(0, 0), (width, 180)], fill=(30, 41, 59))
    draw.text((60, 50), "ACME CLOUD SOLUTIONS PVT LTD", fill=(255, 255, 255))
    draw.text((60, 90), "Enterprise IT Infrastructure & Cloud Hosting", fill=(203, 213, 225))
    draw.text((60, 120), "Bangalore, Karnataka, India | billing@acmecloud.com | +91 9876543210", fill=(148, 163, 184))

    # Invoice Details Block
    draw.rectangle([(60, 220), (width - 60, 360)], fill=(248, 250, 252), outline=(226, 232, 240))
    draw.text((80, 240), "TAX INVOICE", fill=(15, 23, 42))
    draw.text((80, 275), "Invoice No: INV-2025-9014", fill=(15, 23, 42))
    draw.text((80, 305), "Invoice Date: 15/01/2025", fill=(71, 85, 105))
    draw.text((80, 330), "Due Date: 30/01/2025", fill=(71, 85, 105))

    draw.text((650, 240), "BILLED TO (CUSTOMER):", fill=(15, 23, 42))
    draw.text((650, 275), "Apex Global Logistics Inc", fill=(15, 23, 42))
    draw.text((650, 305), "Contact: rahul.verma@apexlogistics.com", fill=(71, 85, 105))
    draw.text((650, 330), "Phone: +91 9811223344 | PAN: ABCDE1234F", fill=(71, 85, 105))

    # Table Header
    draw.rectangle([(60, 420), (width - 60, 470)], fill=(241, 245, 249))
    draw.text((80, 435), "Item Description", fill=(15, 23, 42))
    draw.text((600, 435), "Qty", fill=(15, 23, 42))
    draw.text((750, 435), "Unit Price", fill=(15, 23, 42))
    draw.text((950, 435), "Total Amount", fill=(15, 23, 42))

    # Line Items
    items = [
        ("Cloud Dedicated Cluster Hosting (Standard Tier)", "1", "INR 65,000.00", "INR 65,000.00"),
        ("Kubernetes Production Operations & Maintenance", "1", "INR 30,000.00", "INR 30,000.00"),
        ("Automated Secure Backups & Disaster Recovery", "1", "INR 15,000.00", "INR 15,000.00"),
        ("24/7 Enterprise SLA Support Package", "1", "INR 10,000.00", "INR 10,000.00"),
    ]

    y = 500
    for desc, qty, rate, amt in items:
        draw.text((80, y), desc, fill=(51, 65, 85))
        draw.text((610, y), qty, fill=(51, 65, 85))
        draw.text((750, y), rate, fill=(51, 65, 85))
        draw.text((950, y), amt, fill=(51, 65, 85))
        y += 50
        draw.line([(60, y - 10), (width - 60, y - 10)], fill=(241, 245, 249))

    # Totals Block
    draw.rectangle([(650, y + 20), (width - 60, y + 200)], fill=(248, 250, 252), outline=(226, 232, 240))
    draw.text((680, y + 40), "Subtotal:", fill=(71, 85, 105))
    draw.text((950, y + 40), "INR 120,000.00", fill=(15, 23, 42))

    draw.text((680, y + 80), "GST (18%):", fill=(71, 85, 105))
    draw.text((950, y + 80), "INR 21,600.00", fill=(15, 23, 42))

    draw.text((680, y + 130), "Grand Total Amount:", fill=(15, 23, 42))
    draw.text((950, y + 130), "INR 141,600.00", fill=(37, 99, 235))

    # Remittance Info with PII
    y_bank = y + 240
    draw.text((60, y_bank), "PAYMENT INSTRUCTIONS & REMITTANCE DETAILS:", fill=(15, 23, 42))
    draw.text((60, y_bank + 35), "Bank: State Bank of India | Branch: Koramangala, Bangalore", fill=(71, 85, 105))
    draw.text((60, y_bank + 65), "Account Number: 9182736450192 | IFSC: SBIN0001234", fill=(71, 85, 105))
    draw.text((60, y_bank + 95), "Authorized Signatory: Vikram Malhotra | PAN: AABCA1234F", fill=(71, 85, 105))

    img.save(png_path)

    # Convert to PDF via PyMuPDF
    doc = fitz.open()
    rect = fitz.Rect(0, 0, width, height)
    page = doc.new_page(width=width, height=height)
    page.insert_image(rect, filename=str(png_path))
    doc.save(str(pdf_path))
    doc.close()
    print(f"Created {pdf_path} and {png_path}")


def create_contract():
    pdf_path = SAMPLE_DIR / "sample_contract.pdf"
    png_path = SAMPLE_DIR / "sample_contract.png"

    width, height = 1200, 1600
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (width, 140)], fill=(15, 23, 42))
    draw.text((60, 45), "MASTER SERVICES & NON-DISCLOSURE AGREEMENT", fill=(255, 255, 255))
    draw.text((60, 85), "Contract Reference: MSA-2025-4401 | Effective Date: 01/02/2025", fill=(203, 213, 225))

    y = 180
    contract_text = [
        ("1. PARTIES TO THIS AGREEMENT", True),
        ("This Master Services Agreement ('Agreement') is entered into by and between:", False),
        ("Party 1: Vertex Global Technologies LLC, having registered offices at Silicon Oasis, Mumbai.", False),
        ("Party 2: Horizon Financial Services Ltd, having registered offices at Connaught Place, New Delhi.", False),
        ("Represented by authorized signatory: Rajesh Singhania (Email: rajesh.s@horizonfin.com, Phone: +91 9822334455).", False),
        ("", False),
        ("2. CONFIDENTIALITY & DATA PROTECTION", True),
        ("Both parties agree that all customer data, source code, and financial records shared under this contract", False),
        ("shall be treated as Confidential Information under the Information Technology Act and applicable data protection regulations.", False),
        ("Neither party shall disclose customer PII including PAN cards, Aadhaar identity documents, or bank details to any third party.", False),
        ("", False),
        ("3. TERM & TERMINATION", True),
        ("The effective date of this agreement is 01/02/2025. The initial term shall be 24 months, with an expiry date of 31/01/2027.", False),
        ("Either party may terminate this agreement with 60 days written notice.", False),
        ("", False),
        ("4. GOVERNING LAW & ARBITRATION", True),
        ("This Agreement shall be governed by and construed in accordance with the laws of India.", False),
        ("Any dispute shall be referred to arbitration in Mumbai, Maharashtra.", False),
        ("", False),
        ("IN WITNESS WHEREOF, the parties hereto have executed this Agreement as of the date first written above.", False),
        ("", False),
        ("Signed for Vertex Global: __________________          Signed for Horizon Fin: __________________", False),
    ]

    for line, is_bold in contract_text:
        if is_bold:
            draw.text((60, y), line, fill=(15, 23, 42))
            y += 35
        else:
            draw.text((60, y), line, fill=(51, 65, 85))
            y += 28

    img.save(png_path)

    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(fitz.Rect(0, 0, width, height), filename=str(png_path))
    doc.save(str(pdf_path))
    doc.close()
    print(f"Created {pdf_path} and {png_path}")


def create_identity():
    pdf_path = SAMPLE_DIR / "sample_identity.pdf"
    png_path = SAMPLE_DIR / "sample_identity.png"

    width, height = 1200, 1600
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Card background
    draw.rectangle([(100, 100), (width - 100, 750)], fill=(248, 250, 252), outline=(203, 213, 225), width=3)
    draw.rectangle([(100, 100), (width - 100, 220)], fill=(234, 88, 12))  # Saffron header

    draw.text((140, 125), "GOVERNMENT OF INDIA / REPUBLIQUE DE L'INDE", fill=(255, 255, 255))
    draw.text((140, 165), "UNIQUE IDENTIFICATION AUTHORITY OF INDIA - AADHAAR", fill=(255, 255, 255))

    # Card Content
    draw.rectangle([(140, 260), (340, 500)], fill=(226, 232, 240), outline=(148, 163, 184))
    draw.text((190, 360), "[ PHOTO ]", fill=(100, 116, 139))

    draw.text((380, 260), "Name: Rahul Sharma", fill=(15, 23, 42))
    draw.text((380, 305), "Date of Birth: 14/08/1988", fill=(51, 65, 85))
    draw.text((380, 350), "Gender: Male", fill=(51, 65, 85))
    draw.text((380, 395), "Address: Flat 402, Green Valley Apartments, Indiranagar, Bangalore 560038", fill=(51, 65, 85))
    draw.text((380, 440), "Phone: 9876543210 | Email: rahul.sharma@example.com", fill=(51, 65, 85))

    # Aadhaar Number
    draw.rectangle([(140, 540), (width - 140, 640)], fill=(254, 243, 199), outline=(245, 158, 11))
    draw.text((320, 570), "2847  9182  4301", fill=(180, 83, 9))

    # PAN Card section below
    draw.rectangle([(100, 850), (width - 100, 1450)], fill=(240, 249, 255), outline=(186, 230, 253), width=3)
    draw.rectangle([(100, 850), (width - 100, 960)], fill=(2, 132, 199))

    draw.text((140, 875), "INCOME TAX DEPARTMENT - GOVT. OF INDIA", fill=(255, 255, 255))
    draw.text((140, 915), "PERMANENT ACCOUNT NUMBER (PAN CARD)", fill=(255, 255, 255))

    draw.text((140, 1000), "Name: RAHUL SHARMA", fill=(15, 23, 42))
    draw.text((140, 1050), "Father's Name: SURESH SHARMA", fill=(51, 65, 85))
    draw.text((140, 1100), "Date of Birth: 14/08/1988", fill=(51, 65, 85))

    draw.rectangle([(140, 1180), (width - 140, 1280)], fill=(224, 242, 254), outline=(56, 189, 248))
    draw.text((380, 1210), "ABCDE1234F", fill=(3, 105, 161))

    img.save(png_path)

    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(fitz.Rect(0, 0, width, height), filename=str(png_path))
    doc.save(str(pdf_path))
    doc.close()
    print(f"Created {pdf_path} and {png_path}")


def create_application():
    pdf_path = SAMPLE_DIR / "sample_application.pdf"
    png_path = SAMPLE_DIR / "sample_application.png"

    width, height = 1200, 1600
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (width, 140)], fill=(37, 99, 235))
    draw.text((60, 45), "GLOBAL TECH ENTERPRISES - EMPLOYMENT APPLICATION FORM", fill=(255, 255, 255))
    draw.text((60, 85), "Position Applied: Senior Cloud & AI Solutions Architect | Date: 10/02/2025", fill=(219, 234, 254))

    y = 180
    draw.text((60, y), "PERSONAL & CONTACT DETAILS", fill=(15, 23, 42))
    y += 40
    draw.text((60, y), "Applicant Name: Priya Nair", fill=(51, 65, 85))
    draw.text((600, y), "Email: priya.nair@example.com", fill=(51, 65, 85))
    y += 35
    draw.text((60, y), "Phone: +91 9876501234", fill=(51, 65, 85))
    draw.text((600, y), "Date of Birth: 22/05/1992", fill=(51, 65, 85))
    y += 35
    draw.text((60, y), "Permanent Address: 12A Palm Grove, Whitefield, Bangalore, Karnataka 560066", fill=(51, 65, 85))

    y += 60
    draw.text((60, y), "IDENTIFICATION & FINANCIAL VERIFICATION", fill=(15, 23, 42))
    y += 40
    draw.text((60, y), "Aadhaar Number: 4918 2039 4812", fill=(51, 65, 85))
    draw.text((600, y), "PAN Number: BCDFG5678H", fill=(51, 65, 85))
    y += 35
    draw.text((60, y), "Bank Account for Payroll: 987612345098 | IFSC: HDFC0001428", fill=(51, 65, 85))

    y += 60
    draw.text((60, y), "WORK EXPERIENCE & QUALIFICATIONS", fill=(15, 23, 42))
    y += 40
    draw.text((60, y), "Current Employer: Infosys Technologies Ltd | Total Experience: 9 Years", fill=(51, 65, 85))
    y += 35
    draw.text((60, y), "Highest Qualification: M.Tech in Computer Science, IIT Madras", fill=(51, 65, 85))

    y += 80
    draw.text((60, y), "DECLARATION:", fill=(15, 23, 42))
    y += 30
    draw.text((60, y), "I hereby declare that all particulars furnished in this application form are true and accurate to the best of my knowledge.", fill=(71, 85, 105))
    y += 40
    draw.text((60, y), "Applicant Signature: Priya Nair                       Date: 10/02/2025", fill=(15, 23, 42))

    img.save(png_path)

    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(fitz.Rect(0, 0, width, height), filename=str(png_path))
    doc.save(str(pdf_path))
    doc.close()
    print(f"Created {pdf_path} and {png_path}")


if __name__ == "__main__":
    create_invoice()
    create_contract()
    create_identity()
    create_application()
    print("All sample documents successfully generated!")

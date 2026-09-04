import asyncio
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "backend"))

from app.config import settings
from app.database import db
from app.utils.security import get_password_hash
from app.api.security import DEFAULT_RULES
from app.services.document_service import document_service


class DummyUploadFile:
    """Mock UploadFile for pipeline seeding."""
    def __init__(self, file_path: Path):
        self.filename = file_path.name
        self.file = open(file_path, "rb")


async def seed():
    print("Connecting to database...")
    await db.connect()

    # 1. Seed Admin User
    admin_email = "admin@docintel.ai"
    existing_user = await db.users.find_one({"email": admin_email})
    if not existing_user:
        await db.users.insert_one({
            "email": admin_email,
            "full_name": "DocIntel Administrator",
            "password_hash": get_password_hash("Admin@12345"),
            "role": "admin",
            "created_at": "2025-01-01T00:00:00",
            "updated_at": "2025-01-01T00:00:00",
        })
        print(f"Created default admin user: {admin_email} / Admin@12345")
    else:
        print(f"Admin user {admin_email} already exists.")

    # 2. Seed Default Security Rules
    for rule in DEFAULT_RULES:
        existing_rule = await db.security_rules.find_one({"rule_id": rule["rule_id"]})
        if not existing_rule:
            r = dict(rule)
            r["created_at"] = "2025-01-01T00:00:00"
            r["updated_at"] = "2025-01-01T00:00:00"
            await db.security_rules.insert_one(r)
            print(f"Created security rule: {rule['name']}")
        else:
            print(f"Security rule {rule['name']} already exists.")

    # 3. Process Sample Documents if none are processed yet
    doc_count = await db.documents.count_documents({})
    if doc_count == 0:
        sample_files = [
            BASE_DIR / "data" / "sample_documents" / "sample_invoice.pdf",
            BASE_DIR / "data" / "sample_documents" / "sample_contract.pdf",
            BASE_DIR / "data" / "sample_documents" / "sample_identity.pdf",
            BASE_DIR / "data" / "sample_documents" / "sample_application.pdf",
        ]

        for s_file in sample_files:
            if s_file.exists():
                print(f"\nProcessing sample document: {s_file.name}...")
                dummy = DummyUploadFile(s_file)
                try:
                    result = await document_service.process_document_file(dummy, current_user_email=admin_email)
                    print(f"Processed {result['document_id']}: {result['document_type']} - Status: {result['status']} (Conf: {result['confidence']:.2f})")
                finally:
                    dummy.file.close()

    print("\nDatabase seeding completed successfully!")
    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(seed())

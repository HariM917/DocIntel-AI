from datetime import datetime
from typing import List
from fastapi import APIRouter, HTTPException, Depends

from app.database import db
from app.schemas.security import SecurityRule, SecurityRuleUpdate
from app.utils.security import get_current_user_optional

router = APIRouter(prefix="/security", tags=["Security Rules"])

DEFAULT_RULES = [
    {
        "rule_id": "rule_aadhaar",
        "name": "Aadhaar Masking",
        "entity_type": "AADHAAR",
        "enabled": True,
        "description": "Masks 12-digit Indian Aadhaar numbers to show only the last 4 digits (e.g. XXXX XXXX 9012).",
        "mask_pattern": "XXXX XXXX {last4}",
    },
    {
        "rule_id": "rule_pan",
        "name": "PAN Masking",
        "entity_type": "PAN",
        "enabled": True,
        "description": "Masks 10-character Indian Permanent Account Numbers (e.g. XXXXX1234F).",
        "mask_pattern": "XXXXX{last5}",
    },
    {
        "rule_id": "rule_email",
        "name": "Email Masking",
        "entity_type": "EMAIL",
        "enabled": True,
        "description": "Masks personal and corporate email addresses (e.g. r***@example.com).",
        "mask_pattern": "{first}***@{domain}",
    },
    {
        "rule_id": "rule_phone",
        "name": "Phone Masking",
        "entity_type": "PHONE",
        "enabled": True,
        "description": "Masks primary digits of mobile and telephone numbers (e.g. ******3210).",
        "mask_pattern": "******{last4}",
    },
    {
        "rule_id": "rule_bank_account",
        "name": "Bank Account Masking",
        "entity_type": "BANK_ACCOUNT",
        "enabled": True,
        "description": "Masks account numbers in bank statements and payment records.",
        "mask_pattern": "********{last4}",
    },
    {
        "rule_id": "rule_credit_card",
        "name": "Credit Card Masking",
        "entity_type": "CREDIT_CARD",
        "enabled": True,
        "description": "PCI-DSS compliant masking of credit and debit card numbers (XXXX-XXXX-XXXX-1234).",
        "mask_pattern": "XXXX-XXXX-XXXX-{last4}",
    },
]


async def ensure_default_rules():
    """Seeds default security rules into MongoDB if none exist."""
    count = await db.security_rules.count_documents({})
    if count == 0:
        now = datetime.utcnow().isoformat()
        for rule in DEFAULT_RULES:
            r = dict(rule)
            r["created_at"] = now
            r["updated_at"] = now
            await db.security_rules.insert_one(r)


@router.get("/rules", response_model=List[SecurityRule])
async def get_security_rules():
    await ensure_default_rules()
    cursor = db.security_rules.find({})
    rules = await cursor.to_list(length=100)
    for r in rules:
        if "_id" in r:
            r["_id"] = str(r["_id"])
    return rules


@router.put("/rules/{rule_id}", response_model=SecurityRule)
async def update_security_rule(
    rule_id: str,
    update_data: SecurityRuleUpdate,
    user: dict = Depends(get_current_user_optional),
):
    await ensure_default_rules()
    existing = await db.security_rules.find_one({"rule_id": rule_id})
    if not existing:
        raise HTTPException(status_code=404, detail=f"Security rule '{rule_id}' not found")

    update_fields = {}
    if update_data.enabled is not None:
        update_fields["enabled"] = update_data.enabled
    if update_data.description is not None:
        update_fields["description"] = update_data.description
    if update_data.mask_pattern is not None:
        update_fields["mask_pattern"] = update_data.mask_pattern

    update_fields["updated_at"] = datetime.utcnow().isoformat()

    await db.security_rules.update_one({"rule_id": rule_id}, {"$set": update_fields})
    updated = await db.security_rules.find_one({"rule_id": rule_id})
    if "_id" in updated:
        updated["_id"] = str(updated["_id"])
    return updated

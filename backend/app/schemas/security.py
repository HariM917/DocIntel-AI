from typing import Optional
from pydantic import BaseModel


class SecurityRule(BaseModel):
    rule_id: str
    name: str
    entity_type: str  # AADHAAR, PAN, EMAIL, PHONE, BANK_ACCOUNT, CREDIT_CARD
    enabled: bool = True
    description: str
    mask_pattern: str  # e.g. "XXXX XXXX {last4}"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SecurityRuleUpdate(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[str] = None
    mask_pattern: Optional[str] = None

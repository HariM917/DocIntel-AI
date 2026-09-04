from typing import Optional
from pydantic import BaseModel, Field


class SecurityRuleModel(BaseModel):
    id: Optional[str] = None
    rule_id: str
    name: str
    entity_type: str  # AADHAAR, PAN, EMAIL, PHONE, BANK_ACCOUNT, CREDIT_CARD
    enabled: bool = True
    description: str
    mask_pattern: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        populate_by_name = True

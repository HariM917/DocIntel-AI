from typing import Optional
from pydantic import BaseModel, EmailStr, Field


class UserModel(BaseModel):
    id: Optional[str] = None
    email: EmailStr
    full_name: str
    password_hash: str
    role: str = "user"  # "admin" | "user" | "auditor"
    is_active: bool = True
    created_at: str
    updated_at: str

    class Config:
        populate_by_name = True

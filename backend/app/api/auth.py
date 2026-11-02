import logging
import uuid
from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends

from app.config import settings
from app.database import db
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserResponse
from app.utils.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user,
    is_user_active,
)

logger = logging.getLogger("docintel.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _to_user_response(user: dict) -> dict:
    user_id = str(user.get("user_id") or user.get("_id") or user.get("id") or "")
    return {
        "id": user_id,
        "email": user["email"],
        "full_name": user.get("full_name", user["email"]),
        "role": user.get("role", "user"),
        "status": user.get("status", "active"),
        "organization_id": user.get("organization_id"),
        "created_at": user.get("created_at", datetime.utcnow().isoformat()),
    }


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister):
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    now = datetime.utcnow().isoformat()
    # New registrations are always plain users. Administrator accounts must be
    # provisioned through the explicit, environment-controlled bootstrap flow.
    new_user = {
        "user_id": uuid.uuid4().hex,
        "email": user_data.email,
        "full_name": user_data.full_name,
        "password_hash": get_password_hash(user_data.password),
        "role": "user",
        "status": "active",
        "organization_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    await db.users.insert_one(new_user)

    access_token = create_access_token(data={"sub": new_user["email"], "role": new_user["role"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": _to_user_response(new_user),
    }


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email})
    if not user or not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not is_user_active(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )

    access_token = create_access_token(data={"sub": user["email"], "role": user.get("role", "user")})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": _to_user_response(user),
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return _to_user_response(current_user)


async def ensure_bootstrap_admin() -> None:
    """Idempotently provisions a bootstrap administrator from environment config.

    This is the ONLY supported path to admin creation. Credentials are sourced
    solely from environment variables and are never logged or returned.
    """
    email = (settings.BOOTSTRAP_ADMIN_EMAIL or "").strip()
    password = settings.BOOTSTRAP_ADMIN_PASSWORD or ""
    if not email or not password:
        return

    existing = await db.users.find_one({"email": email})
    now = datetime.utcnow().isoformat()
    if existing:
        if existing.get("role") != "admin":
            await db.users.update_one(
                {"email": email},
                {"$set": {"role": "admin", "status": "active", "is_active": True, "updated_at": now}},
            )
            logger.info("Bootstrap admin privileges ensured for configured account.")
        return

    await db.users.insert_one({
        "user_id": uuid.uuid4().hex,
        "email": email,
        "full_name": "Bootstrap Administrator",
        "password_hash": get_password_hash(password),
        "role": "admin",
        "status": "active",
        "organization_id": None,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    })
    logger.info("Bootstrap administrator account created from environment configuration.")

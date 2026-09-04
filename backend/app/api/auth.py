from datetime import datetime
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import EmailStr

from app.database import db
from app.schemas.auth import UserRegister, UserLogin, TokenResponse, UserResponse
from app.utils.security import verify_password, get_password_hash, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserRegister):
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists."
        )

    now = datetime.utcnow().isoformat()
    new_user = {
        "email": user_data.email,
        "full_name": user_data.full_name,
        "password_hash": get_password_hash(user_data.password),
        "role": "admin" if (await db.users.count_documents({})) == 0 else "user",
        "created_at": now,
        "updated_at": now,
    }

    insert_result = await db.users.insert_one(new_user)
    user_id = str(insert_result.inserted_id)

    access_token = create_access_token(data={"sub": user_data.email, "role": new_user["role"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": new_user["email"],
            "full_name": new_user["full_name"],
            "role": new_user["role"],
            "created_at": new_user["created_at"],
        }
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

    user_id = str(user.get("_id", user.get("id", "")))
    access_token = create_access_token(data={"sub": user["email"], "role": user.get("role", "user")})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "email": user["email"],
            "full_name": user.get("full_name", user["email"]),
            "role": user.get("role", "user"),
            "created_at": user.get("created_at", datetime.utcnow().isoformat()),
        }
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user.get("_id", current_user.get("id", "")))
    return {
        "id": user_id,
        "email": current_user["email"],
        "full_name": current_user.get("full_name", current_user["email"]),
        "role": current_user.get("role", "user"),
        "created_at": current_user.get("created_at", datetime.utcnow().isoformat()),
    }

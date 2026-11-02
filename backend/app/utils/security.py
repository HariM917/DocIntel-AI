from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import bcrypt

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

security_scheme = HTTPBearer(auto_error=False)

# Account statuses that are allowed to access protected resources.
ACTIVE_STATUSES = {"active"}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None


def get_user_id(user: dict) -> str:
    """Returns the stable identifier for a user document.

    Prefers the explicit immutable ``user_id`` field, falling back to legacy
    identifiers for accounts created before this field was introduced.
    """
    return str(user.get("user_id") or user.get("_id") or user.get("id") or user.get("email"))


def is_user_active(user: dict) -> bool:
    """Determines whether an account is allowed to access protected resources."""
    raw_status = user.get("status")
    if raw_status is None:
        # Legacy accounts: fall back to the boolean is_active flag.
        return user.get("is_active", True) is not False
    return str(raw_status).strip().lower() in ACTIVE_STATUSES


def authorization_filter(user: dict) -> dict:
    """Builds a MongoDB filter restricting documents to those ``user`` may access.

    Delegates to the centralized authorization policy so that owner, legacy
    owner-email and organization-membership rules are defined in exactly one
    place (see :mod:`app.services.authorization_service`).
    """
    from app.services.authorization_service import document_access_filter
    return document_access_filter(user)


async def _load_user_by_subject(subject: str) -> Optional[dict]:
    from app.database import db
    return await db.users.find_one({"email": subject})


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme)
) -> dict:
    """Authenticates the caller and verifies the account is active."""
    if not auth:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(auth.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await _load_user_by_subject(payload["sub"])
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not is_user_active(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return user


async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency for protected routes that require an active account."""
    if not is_user_active(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active",
        )
    return current_user


async def get_authorized_document(document_id: str, current_user: dict) -> dict:
    """Fetches a document only if the authenticated user is authorized to access it.

    Delegates to the centralized authorization helper. Raises 404 (never
    leaking existence of another user's document) when the document does not
    exist or the caller is not authorized.
    """
    from app.services.authorization_service import authorize_document_access
    return await authorize_document_access(document_id, current_user)

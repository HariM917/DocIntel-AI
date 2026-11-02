"""Centralized document authorization (production stabilization).

Every document operation (read, status, download, delete, reprocess, search,
chat/RAG, dashboard aggregation) is authorized through this single module.
No endpoint may resolve a document by ``document_id`` alone.

Authorization policy (Phase 3 stabilization §3):

    access is granted when ANY of the following holds
        * document.owner_id          == current_user.id            (primary owner)
        * document.owner (email)     == current_user.email         (legacy accounts)
        * document.organization_id   == current_user.organization_id
          AND both values are non-empty (organization membership sharing)

The caller's identity is always derived from the authenticated user record.
Client-supplied ``owner_id`` / ``organization_id`` values are never trusted.

The organization clause is only added when the caller actually belongs to an
organization, so personal documents (which carry ``organization_id = None``)
never become visible to unrelated callers.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("docintel.authorization")


def user_identifier(user: Optional[dict]) -> Optional[str]:
    """Returns the stable identifier for an authenticated user document."""
    if not user:
        return None
    return str(
        user.get("user_id")
        or user.get("_id")
        or user.get("id")
        or user.get("email")
        or ""
    ) or None


def user_email(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    value = user.get("email")
    return str(value) if value else None


def user_organization(user: Optional[dict]) -> Optional[str]:
    if not user:
        return None
    value = user.get("organization_id")
    return str(value) if value else None


def can_access_document(document: Optional[dict], user: Optional[dict]) -> bool:
    """Returns True when ``user`` is authorized to access ``document``."""
    if not document or not user:
        return False

    uid = user_identifier(user)
    email = user_email(user)
    org = user_organization(user)

    doc_owner_id = document.get("owner_id")
    doc_owner = document.get("owner")
    doc_org = document.get("organization_id")

    if uid and doc_owner_id and str(doc_owner_id) == uid:
        return True
    if email and doc_owner and str(doc_owner) == email:
        return True
    # Organization sharing requires BOTH sides to be a real, non-empty org id.
    if org and doc_org and str(doc_org) == org:
        return True
    return False


def can_modify_document(document: Optional[dict], user: Optional[dict]) -> bool:
    """Modifying a document follows the same access policy as reading it."""
    return can_access_document(document, user)


def can_delete_document(document: Optional[dict], user: Optional[dict]) -> bool:
    """Deleting a document follows the same access policy as reading it."""
    return can_access_document(document, user)


def can_reprocess_document(document: Optional[dict], user: Optional[dict]) -> bool:
    """Reprocessing a document follows the same access policy as reading it."""
    return can_access_document(document, user)


def can_access_chunk(
    metadata: Optional[Dict[str, Any]],
    *,
    owner_id: Optional[str] = None,
    owner_email: Optional[str] = None,
    organization_id: Optional[str] = None,
) -> bool:
    """Authorizes a single FAISS chunk's metadata against a caller context.

    Fails closed: a chunk that carries no ownership metadata at all (legacy
    index entries) is never authorized. Uses the exact same policy as
    :func:`can_access_document`.
    """
    if not metadata:
        return False
    return can_access_document(
        {
            "owner_id": metadata.get("owner_id"),
            "owner": metadata.get("owner"),
            "organization_id": metadata.get("organization_id"),
        },
        {
            "user_id": owner_id,
            "email": owner_email,
            "organization_id": organization_id,
        },
    )


def document_access_filter(user: dict) -> dict:
    """Builds a MongoDB filter restricting documents to those ``user`` may access.

    Matches the stable ``owner_id`` when present, falls back to the legacy
    ``owner`` (email) field for pre-migration accounts, and — only when the
    caller belongs to an organization — also matches documents shared with that
    organization.
    """
    clauses: List[Dict[str, Any]] = [{"owner": user_email(user)}]
    uid = user_identifier(user)
    if uid:
        clauses.append({"owner_id": uid})
    org = user_organization(user)
    if org:
        # Never emit {"organization_id": None}: that would match personal
        # documents which carry no organization.
        clauses.append({"organization_id": org})
    return {"$or": clauses}


async def authorize_document_access(document_id: str, user: dict) -> dict:
    """Loads a document only if ``user`` is authorized; raises 404 otherwise.

    A 404 (rather than 403) is returned so the existence of another user's
    document is never disclosed. This is the single helper every service must
    use before touching document-derived data.
    """
    from fastapi import HTTPException, status

    from app.database import db

    query = {"$and": [{"document_id": document_id}, document_access_filter(user)]}
    document = await db.documents.find_one(query)
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )
    return document

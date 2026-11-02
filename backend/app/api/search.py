import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, Depends, HTTPException

from app.config import settings
from app.database import db
from app.utils.security import authorization_filter, get_current_active_user

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("")
async def search_documents(
    q: str = Query(..., min_length=1, description="Search query string"),
    current_user: dict = Depends(get_current_active_user),
):
    query_str = q.strip()
    if not query_str:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    if len(query_str) > settings.MAX_SEARCH_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Search query exceeds maximum length of {settings.MAX_SEARCH_QUERY_LENGTH} characters",
        )

    # Escape user input so it cannot inject regex operators or widen the match set.
    safe_query = re.escape(query_str)

    search_filter = {
        "$or": [
            {"document_id": {"$regex": safe_query, "$options": "i"}},
            {"filename": {"$regex": safe_query, "$options": "i"}},
            {"document_type": {"$regex": safe_query, "$options": "i"}},
            {"raw_text": {"$regex": safe_query, "$options": "i"}},
            {"redacted_text": {"$regex": safe_query, "$options": "i"}},
            {"entities.text": {"$regex": safe_query, "$options": "i"}},
            {"pii_entities.value": {"$regex": safe_query, "$options": "i"}},
        ]
    }

    # Authorization filter is ANDed with the search filter and cannot be bypassed
    # by regex conditions supplied through the query string.
    mongo_query = {"$and": [authorization_filter(current_user), search_filter]}

    cursor = db.documents.find(mongo_query).sort("created_at", -1).limit(25)
    matched_docs = await cursor.to_list(length=25)

    results = []
    for doc in matched_docs:
        # Create snippet with query highlight
        text = doc.get("redacted_text") or doc.get("raw_text") or ""
        snippet = ""
        idx = text.lower().find(query_str.lower())
        if idx >= 0:
            start = max(0, idx - 60)
            end = min(len(text), idx + len(query_str) + 60)
            snippet = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
        else:
            snippet = text[:120] + ("..." if len(text) > 120 else "")

        results.append({
            "id": str(doc.get("_id", doc.get("id", ""))),
            "document_id": doc.get("document_id"),
            "filename": doc.get("filename"),
            "document_type": doc.get("document_type"),
            "status": doc.get("status"),
            "confidence": doc.get("confidence"),
            "created_at": doc.get("created_at"),
            "snippet": snippet,
        })

    return {
        "query": query_str,
        "total_matches": len(results),
        "results": results,
    }

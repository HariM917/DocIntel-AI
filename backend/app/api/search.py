from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query

from app.database import db

router = APIRouter(prefix="/search", tags=["Search"])


@router.get("")
async def search_documents(
    q: str = Query(..., min_length=1, description="Search query string")
):
    query_str = q.strip()
    mongo_query = {
        "$or": [
            {"document_id": {"$regex": query_str, "$options": "i"}},
            {"filename": {"$regex": query_str, "$options": "i"}},
            {"document_type": {"$regex": query_str, "$options": "i"}},
            {"raw_text": {"$regex": query_str, "$options": "i"}},
            {"redacted_text": {"$regex": query_str, "$options": "i"}},
            {"entities.text": {"$regex": query_str, "$options": "i"}},
            {"pii_entities.value": {"$regex": query_str, "$options": "i"}},
        ]
    }

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

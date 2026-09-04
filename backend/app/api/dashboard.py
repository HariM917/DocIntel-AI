from typing import List, Dict, Any
from fastapi import APIRouter

from app.database import db
from app.schemas.dashboard import DashboardStats, RecentDocumentItem

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    cursor = db.documents.find({}).sort("created_at", -1)
    all_docs = await cursor.to_list(length=1000)

    total_processed = len(all_docs)

    if total_processed == 0:
        return {
            "total_processed": 0,
            "extraction_accuracy": 0.0,
            "protected_entities": 0,
            "time_saved": "0 hrs",
            "type_distribution": {},
            "status_distribution": {},
            "recent_documents": [],
        }

    # Extraction Accuracy
    confidences = [d.get("confidence", 0.85) for d in all_docs if "confidence" in d]
    avg_accuracy = round((sum(confidences) / len(confidences)) * 100.0, 1) if confidences else 95.0

    # Protected Entities count
    total_protected = 0
    type_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}

    for d in all_docs:
        # PII entities count
        piis = d.get("pii_entities", [])
        total_protected += len([p for p in piis if p.get("sensitive", False)])

        # Type breakdown
        dtype = d.get("document_type", "Other")
        type_counts[dtype] = type_counts.get(dtype, 0) + 1

        # Status breakdown
        st = d.get("status", "Verified")
        status_counts[st] = status_counts.get(st, 0) + 1

    # Time Saved estimation:
    # Manual data entry & verification: ~6 minutes per document
    # Automated processing: ~2.5 seconds per document
    # Net saved = ~5.95 minutes per document
    total_minutes_saved = total_processed * 6.0
    if total_minutes_saved < 60:
        time_saved_str = f"{int(total_minutes_saved)} mins"
    else:
        time_saved_str = f"{round(total_minutes_saved / 60.0, 1)} hrs"

    # Recent Documents (latest 6)
    recent_items: List[RecentDocumentItem] = []
    for d in all_docs[:6]:
        # Extract vendor/name
        vendor_or_name = "N/A"
        struct = d.get("structured_data", {})
        if "vendor_name" in struct and struct["vendor_name"] != "N/A":
            vendor_or_name = struct["vendor_name"]
        elif "name" in struct and struct["name"] != "N/A":
            vendor_or_name = struct["name"]
        elif "applicant_name" in struct and struct["applicant_name"] != "N/A":
            vendor_or_name = struct["applicant_name"]
        elif "parties" in struct and struct["parties"]:
            vendor_or_name = ", ".join(struct["parties"][:2])
        else:
            # Fallback to first entity
            ents = d.get("entities", [])
            if ents:
                vendor_or_name = ents[0].get("text", "N/A")

        recent_items.append(RecentDocumentItem(
            document_id=d.get("document_id", "DOC-UNKNOWN"),
            filename=d.get("filename", "unknown"),
            document_type=d.get("document_type", "Other"),
            extracted_vendor_or_name=vendor_or_name,
            created_at=d.get("created_at", ""),
            status=d.get("status", "Verified"),
            confidence=round(d.get("confidence", 0.90) * 100, 1),
        ))

    return {
        "total_processed": total_processed,
        "extraction_accuracy": avg_accuracy,
        "protected_entities": total_protected,
        "time_saved": time_saved_str,
        "type_distribution": type_counts,
        "status_distribution": status_counts,
        "recent_documents": recent_items,
    }


@router.get("/recent", response_model=List[RecentDocumentItem])
async def get_recent_documents():
    stats = await get_dashboard_stats()
    return stats.recent_documents

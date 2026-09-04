import re
import logging
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger("docintel.ner")

# Mapping model entity labels to internal standardized schema
LABEL_MAPPING = {
    "PER": "PERSON",
    "PERSON": "PERSON",
    "ORG": "ORGANIZATION",
    "ORGANIZATION": "ORGANIZATION",
    "LOC": "LOCATION",
    "LOCATION": "LOCATION",
    "MISC": "MISCELLANEOUS",
    "GPE": "LOCATION",
    "DATE": "DATE",
    "MONEY": "MONEY",
}


class NERService:
    """Named Entity Recognition using fine-tuned RoBERTa token classification pipeline with robust fallback."""

    def __init__(self):
        self.model_name = settings.HF_MODEL_NAME
        self.pipeline = None
        self._initialized = False
        self._init_attempted = False

    def _load_model(self):
        if self._init_attempted:
            return
        self._init_attempted = True
        try:
            logger.info(f"Loading RoBERTa NER pipeline ({self.model_name})...")
            from transformers import pipeline, AutoModelForTokenClassification, AutoTokenizer
            import torch

            device = 0 if torch.cuda.is_available() else -1
            self.pipeline = pipeline(
                "ner",
                model=self.model_name,
                tokenizer=self.model_name,
                aggregation_strategy="simple",
                device=device,
            )
            self._initialized = True
            logger.info(f"RoBERTa NER model '{self.model_name}' loaded successfully on device {device}.")
        except Exception as e:
            logger.warning(
                f"Could not load HuggingFace RoBERTa model '{self.model_name}': {e}. "
                "Engaging resilient fallback heuristic NER engine."
            )
            self.pipeline = None
            self._initialized = False

    def extract_entities(self, text: str) -> List[Dict[str, Any]]:
        """Extracts named entities from text with type normalization and confidence scores."""
        if not text or not text.strip():
            return []

        # Ensure pipeline is loaded (lazy loading)
        self._load_model()

        entities: List[Dict[str, Any]] = []

        if self._initialized and self.pipeline is not None:
            try:
                # RoBERTa maximum context chunking
                # Truncate or chunk if text is extremely long
                max_chunk_chars = 1500
                chunks = [text[i:i + max_chunk_chars] for i in range(0, len(text), max_chunk_chars)]
                
                char_offset = 0
                for chunk in chunks:
                    results = self.pipeline(chunk)
                    for item in results:
                        raw_label = item.get("entity_group") or item.get("entity") or ""
                        # Strip B- / I- prefixes if present
                        cleaned_label = re.sub(r"^[BI]-", "", raw_label).upper()
                        mapped_type = LABEL_MAPPING.get(cleaned_label, cleaned_label or "MISCELLANEOUS")
                        
                        ent_text = item.get("word", "").strip()
                        if ent_text and len(ent_text) > 1:
                            entities.append({
                                "text": ent_text,
                                "type": mapped_type,
                                "confidence": round(float(item.get("score", 0.90)), 4),
                                "start": item.get("start", 0) + char_offset,
                                "end": item.get("end", 0) + char_offset,
                            })
                    char_offset += len(chunk)

                if entities:
                    return self._deduplicate_entities(entities)
            except Exception as e:
                logger.error(f"Error during RoBERTa NER pipeline execution: {e}")

        # Fallback heuristic / pattern-based NER
        fallback_entities = self._fallback_ner(text)
        return self._deduplicate_entities(fallback_entities)

    def _fallback_ner(self, text: str) -> List[Dict[str, Any]]:
        """High-precision pattern extraction for Person, Organization, Location when ML model is offline."""
        entities = []

        # Organization indicators
        org_patterns = [
            r"\b([A-Z][A-Za-z0-9&.\s]{2,30}?(?:Inc|LLC|Ltd|Limited|Corp|Corporation|Technologies|Solutions|Pvt|Private|Systems|Bank|University))\b",
        ]
        for pat in org_patterns:
            for match in re.finditer(pat, text):
                val = match.group(1).strip()
                entities.append({
                    "text": val,
                    "type": "ORGANIZATION",
                    "confidence": 0.88,
                    "start": match.start(1),
                    "end": match.end(1),
                })

        # Person name indicators (e.g. Rahul Sharma, Jane Doe, Dr./Mr./Ms.)
        person_patterns = [
            r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",
            r"(?:Name|Applicant|Vendor|Client|Billed To|Customer)\s*[:.\-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})",
        ]
        for pat in person_patterns:
            for match in re.finditer(pat, text):
                val = match.group(1).strip()
                if not any(stop in val.lower() for stop in ["invoice", "total", "amount", "date", "contract"]):
                    entities.append({
                        "text": val,
                        "type": "PERSON",
                        "confidence": 0.86,
                        "start": match.start(1),
                        "end": match.end(1),
                    })

        # Location indicators (Cities, States, Countries)
        locations = [
            "Mumbai", "Delhi", "Bengaluru", "Bangalore", "Hyderabad", "Chennai", "Kolkata",
            "Pune", "Ahmedabad", "New York", "San Francisco", "London", "Singapore",
            "California", "Texas", "Karnataka", "Maharashtra", "Tamil Nadu", "India", "USA"
        ]
        for loc in locations:
            for match in re.finditer(rf"\b{loc}\b", text, re.IGNORECASE):
                entities.append({
                    "text": match.group(0),
                    "type": "LOCATION",
                    "confidence": 0.92,
                    "start": match.start(0),
                    "end": match.end(0),
                })

        return entities

    def _deduplicate_entities(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []
        for ent in sorted(entities, key=lambda x: x["confidence"], reverse=True):
            key = (ent["text"].lower(), ent["type"])
            if key not in seen:
                seen.add(key)
                deduped.append(ent)
        return deduped


ner_service = NERService()

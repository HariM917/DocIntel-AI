import re
import logging
from typing import List, Dict, Any, Optional

from app.services.validation_service import validation_service

logger = logging.getLogger("docintel.pii")


class PIIService:
    """Detects personally identifiable information (PII) and sensitive financial data

    Combines deterministic regex, contextual boundary checking, and RoBERTa NER outputs.
    """

    # High-precision patterns for sensitive identifiers
    PATTERNS = {
        "AADHAAR": [
            r"\b[2-9][0-9]{3}\s+[0-9]{4}\s+[0-9]{4}\b",
            r"\b[2-9][0-9]{3}-[0-9]{4}-[0-9]{4}\b",
            r"\b[2-9][0-9]{11}\b",
        ],
        "PAN": [
            r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        ],
        "EMAIL": [
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        ],
        "PHONE": [
            r"(?:\+91[\-\s]?)?[6789]\d{9}\b",
            r"\b(?:\+1[\-\s]?)?\(?\d{3}\)?[\-\s]?\d{3}[\-\s]?\d{4}\b",
        ],
        "CREDIT_CARD": [
            r"\b4[0-9]{12}(?:[0-9]{3})?\b",                        # Visa
            r"\b5[1-5][0-9]{14}\b",                                # MasterCard
            r"\b3[47][0-9]{13}\b",                                 # American Express
            r"\b(?:4[0-9]{3}|5[1-5][0-9]{2})[\s\-][0-9]{4}[\s\-][0-9]{4}[\s\-][0-9]{4}\b",
        ],
        "BANK_ACCOUNT": [
            r"(?:A/C|Acc(?:ount)?(?:\s*No\.?)?|Account\s*Number)\s*[:.\-]?\s*([0-9]{9,18})\b",
            r"\b(?:IFSC\s*[:.\-]?\s*[A-Z]{4}0[A-Z0-9]{6})\b",
        ],
        "DATE": [
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
            r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
        ],
        "INVOICE_NUMBER": [
            r"\b(?:INV|Invoice|Bill|Ref)[\s\-_#:]*([A-Z0-9\-_]{4,15})\b",
        ],
    }

    # Sensitive entity types that warrant redaction
    SENSITIVE_TYPES = {
        "AADHAAR", "PAN", "EMAIL", "PHONE", "CREDIT_CARD", "BANK_ACCOUNT"
    }

    def detect_pii(self, text: str, ner_entities: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
        """Scans text for PII entities using regex rules and merges with relevant NER entities."""
        if not text or not text.strip():
            return []

        results: List[Dict[str, Any]] = []

        # 1. Deterministic Pattern Matching
        for entity_type, regex_list in self.PATTERNS.items():
            for pattern in regex_list:
                for match in re.finditer(pattern, text, re.IGNORECASE):
                    # Group 1 if captured, else full match
                    val = match.group(1) if match.groups() else match.group(0)
                    val = val.strip()
                    
                    if not val:
                        continue

                    # Contextual and format validation
                    is_valid, reason = self._validate_entity(entity_type, val)
                    
                    confidence = 0.98 if is_valid else 0.70
                    # Additional confidence boost for clean structured formats
                    if entity_type == "PAN" and is_valid:
                        confidence = 0.99
                    elif entity_type == "EMAIL" and is_valid:
                        confidence = 0.99

                    results.append({
                        "type": entity_type,
                        "value": val,
                        "confidence": confidence,
                        "source": "regex",
                        "sensitive": entity_type in self.SENSITIVE_TYPES,
                        "valid": is_valid,
                        "start": match.start(0),
                        "end": match.end(0),
                    })

        # 2. Integrate NER Entities (e.g. PERSON as sensitive PII)
        if ner_entities:
            for ent in ner_entities:
                ent_type = ent.get("type", "")
                ent_text = ent.get("text", "").strip()

                if not ent_text or len(ent_text) < 2:
                    continue

                if ent_type == "PERSON":
                    results.append({
                        "type": "PERSON",
                        "value": ent_text,
                        "confidence": ent.get("confidence", 0.90),
                        "source": "roberta",
                        "sensitive": True,  # Person names can be treated as sensitive PII
                        "valid": True,
                        "start": ent.get("start"),
                        "end": ent.get("end"),
                    })
                elif ent_type in ["ORGANIZATION", "LOCATION"]:
                    results.append({
                        "type": ent_type,
                        "value": ent_text,
                        "confidence": ent.get("confidence", 0.88),
                        "source": "roberta",
                        "sensitive": False,
                        "valid": True,
                        "start": ent.get("start"),
                        "end": ent.get("end"),
                    })

        # Deduplicate and sort by position
        return self._deduplicate(results)

    def _validate_entity(self, entity_type: str, value: str) -> (bool, str):
        if entity_type == "AADHAAR":
            return validation_service.validate_aadhaar(value)
        elif entity_type == "PAN":
            return validation_service.validate_pan(value)
        elif entity_type == "EMAIL":
            return validation_service.validate_email(value)
        elif entity_type == "PHONE":
            return validation_service.validate_phone(value)
        elif entity_type == "CREDIT_CARD":
            return validation_service.validate_luhn(value), "Luhn verified"
        elif entity_type == "BANK_ACCOUNT":
            return validation_service.validate_bank_account(value)
        return True, "Valid"

    def _deduplicate(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []
        for ent in sorted(entities, key=lambda x: (x.get("start") or 0, -x["confidence"])):
            key = (ent["value"].strip(), ent["type"])
            if key not in seen:
                seen.add(key)
                deduped.append(ent)
        return deduped


pii_service = PIIService()

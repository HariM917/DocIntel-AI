import re
import logging
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("docintel.extraction")

# Provenance vocabulary (Step 24). Every extracted field records *where* its
# value came from so downstream consumers can audit/trace it. Document text is
# always treated as DATA -- never as instructions.
SOURCE_RULE = "rule"            # anchored label/value regex over the document text
SOURCE_NER = "ner"              # named-entity recognition (PERSON/ORGANIZATION/...)
SOURCE_PII = "pii"              # deterministic PII detector (EMAIL/PHONE/AADHAAR/...)
SOURCE_DERIVED = "derived"      # inferred from weak evidence (e.g. currency symbol)
SOURCE_DEFAULT = "default"      # schema default with no in-document evidence
SOURCE_NOT_FOUND = "not_found"  # field genuinely absent

# Fixed, documented confidence priors. Confidence is never invented: a field
# with no measurable evidence yields ``None`` rather than a fabricated score.
_PRIORS: Dict[str, Optional[float]] = {
    SOURCE_RULE: 0.9,       # an explicit field label anchored the value
    SOURCE_PII: 0.85,       # a validated detector match
    SOURCE_DERIVED: 0.6,    # weak inference
    SOURCE_NER: None,       # resolved from the entity's own confidence when known
    SOURCE_DEFAULT: None,
    SOURCE_NOT_FOUND: None,
}


def _meta(source: str, confidence: Optional[float] = None) -> Dict[str, Any]:
    return {"source": source, "confidence": confidence if confidence is not None else _PRIORS.get(source)}


class StructuredExtractionService:
    """Extracts typed, structured key-value schemas based on document category.

    Every field is accompanied by provenance metadata (``source`` + an honest
    ``confidence``) exposed via :meth:`extract_with_metadata`. The flat
    :meth:`extract` return value is unchanged for backward compatibility.
    """

    def extract(
        self,
        document_type: str,
        text: str,
        entities: List[Dict[str, Any]],
        pii_entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return self.extract_with_metadata(document_type, text, entities, pii_entities)["structured_data"]

    def extract_with_metadata(
        self,
        document_type: str,
        text: str,
        entities: List[Dict[str, Any]],
        pii_entities: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Returns ``{"structured_data": {...}, "field_metadata": {...}}``.

        ``field_metadata`` maps each schema field to
        ``{"value", "confidence", "source"}`` where ``confidence`` is ``None``
        when it cannot be computed from actual evidence.
        """
        doc_type = (document_type or "").strip().capitalize()
        if doc_type == "Invoice":
            data, prov = self._extract_invoice(text, entities, pii_entities)
        elif doc_type == "Contract":
            data, prov = self._extract_contract(text, entities, pii_entities)
        elif doc_type == "Identity":
            data, prov = self._extract_identity(text, entities, pii_entities)
        elif doc_type in ["Application", "Form"]:
            data, prov = self._extract_form(text, entities, pii_entities)
        else:
            data, prov = self._extract_generic(text, entities, pii_entities)

        field_metadata = {
            key: {"value": value, "confidence": prov.get(key, {}).get("confidence"),
                  "source": prov.get(key, {}).get("source", SOURCE_NOT_FOUND)}
            for key, value in data.items()
        }
        return {"structured_data": data, "field_metadata": field_metadata}

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _blank(keys: List[str]) -> Dict[str, Dict[str, Any]]:
        return {k: _meta(SOURCE_NOT_FOUND) for k in keys}

    @staticmethod
    def _entity_confidence(entities: List[Dict[str, Any]], value: str, etype: str) -> Optional[float]:
        for ent in entities:
            if ent.get("type") == etype and ent.get("text") == value:
                return ent.get("confidence")
        return None

    @staticmethod
    def _pii_confidence(pii_entities: List[Dict[str, Any]], value: str, ptype: str) -> Optional[float]:
        for pii in pii_entities:
            if pii.get("type") == ptype and (pii.get("value") == value or pii.get("masked_value") == value):
                return pii.get("confidence")
        return None

    # -- invoice -----------------------------------------------------------
    def _extract_invoice(self, text: str, entities, pii_entities) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data: Dict[str, Any] = {
            "invoice_number": "N/A",
            "invoice_date": "N/A",
            "due_date": "N/A",
            "vendor_name": "N/A",
            "customer_name": "N/A",
            "subtotal": "N/A",
            "tax": "N/A",
            "total_amount": "N/A",
            "currency": "INR",
        }
        prov = self._blank(list(data.keys()))

        # 1. Invoice Number
        inv_match = re.search(r"\b(?:invoice|inv)\s*(?:no|number|#|num)?\s*[:.\-#]\s*([A-Z0-9\-_/]+)", text, re.IGNORECASE)
        if not inv_match:
            inv_match = re.search(r"\b(?:invoice|inv)\s+(?:no|number|#|num)\s+([A-Z0-9\-_/]+)", text, re.IGNORECASE)
        if inv_match and inv_match.group(1).upper() not in ["OICE", "DATE", "TAX", "TOTAL"]:
            data["invoice_number"] = inv_match.group(1).strip()
            prov["invoice_number"] = _meta(SOURCE_RULE)
        else:
            for pii in pii_entities:
                if pii.get("type") == "INVOICE_NUMBER":
                    data["invoice_number"] = pii.get("value")
                    prov["invoice_number"] = _meta(SOURCE_PII, self._pii_confidence(pii_entities, pii.get("value"), "INVOICE_NUMBER"))
                    break

        # 2. Currency
        if "$" in text or "USD" in text:
            data["currency"] = "USD"
            prov["currency"] = _meta(SOURCE_DERIVED)
        elif "€" in text or "EUR" in text:
            data["currency"] = "EUR"
            prov["currency"] = _meta(SOURCE_DERIVED)
        elif "£" in text or "GBP" in text:
            data["currency"] = "GBP"
            prov["currency"] = _meta(SOURCE_DERIVED)
        elif "₹" in text or "INR" in text or "Rs" in text:
            data["currency"] = "INR"
            prov["currency"] = _meta(SOURCE_DERIVED)
        else:
            prov["currency"] = _meta(SOURCE_DEFAULT)

        # 3. Total Amount
        total_match = re.search(r"\b(?<!sub)(?:grand\s*total|total\s*amount|amount\s*payable|balance\s*due|total)\s*[:.\-]?\s*[₹$€£Rs.]*\s*([0-9,]+\.[0-9]{2}|[0-9,]+)", text, re.IGNORECASE)
        if total_match:
            data["total_amount"] = total_match.group(1).strip()
            prov["total_amount"] = _meta(SOURCE_RULE)

        # 4. Subtotal
        sub_match = re.search(r"(?:subtotal|sub\s*total|net\s*amount)\s*[:.\-]?\s*[₹$€£Rs.]*\s*([0-9,]+\.[0-9]{2}|[0-9,]+)", text, re.IGNORECASE)
        if sub_match:
            data["subtotal"] = sub_match.group(1).strip()
            prov["subtotal"] = _meta(SOURCE_RULE)

        # 5. Tax / GST / VAT
        tax_match = re.search(r"(?:tax|gst|vat|cgst\s*\+\s*sgst|igst)\s*[:.\-]?\s*[₹$€£Rs.]*\s*([0-9,]+\.[0-9]{2}|[0-9,]+)", text, re.IGNORECASE)
        if tax_match:
            data["tax"] = tax_match.group(1).strip()
            prov["tax"] = _meta(SOURCE_RULE)

        # 6. Dates
        dates = [p["value"] for p in pii_entities if p.get("type") == "DATE"]
        inv_date_match = re.search(r"(?:invoice\s*date|bill\s*date|date)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if inv_date_match:
            data["invoice_date"] = inv_date_match.group(1).strip()
            prov["invoice_date"] = _meta(SOURCE_RULE)
        elif dates:
            data["invoice_date"] = dates[0]
            prov["invoice_date"] = _meta(SOURCE_PII, self._pii_confidence(pii_entities, dates[0], "DATE"))

        due_date_match = re.search(r"(?:due\s*date|payment\s*due)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if due_date_match:
            data["due_date"] = due_date_match.group(1).strip()
            prov["due_date"] = _meta(SOURCE_RULE)
        elif len(dates) > 1 and data["invoice_date"] != dates[1]:
            data["due_date"] = dates[1]
            prov["due_date"] = _meta(SOURCE_PII, self._pii_confidence(pii_entities, dates[1], "DATE"))

        # 7. Vendor Name (often first Organization entity or top of document)
        orgs = [e["text"] for e in entities if e.get("type") == "ORGANIZATION"]
        vendor_match = re.search(r"(?:vendor|from|billed\s*by|supplier)\s*[:.\-]?\s*([A-Za-z0-9&.\s]{3,35})", text, re.IGNORECASE)
        if vendor_match:
            data["vendor_name"] = vendor_match.group(1).strip()
            prov["vendor_name"] = _meta(SOURCE_RULE)
        elif orgs:
            data["vendor_name"] = orgs[0]
            prov["vendor_name"] = _meta(SOURCE_NER, self._entity_confidence(entities, orgs[0], "ORGANIZATION"))

        # 8. Customer / Client Name
        cust_match = re.search(r"(?:bill\s*to|customer|client|sold\s*to)\s*[:.\-]?\s*([A-Za-z0-9&.\s]{3,35})", text, re.IGNORECASE)
        if cust_match:
            data["customer_name"] = cust_match.group(1).strip()
            prov["customer_name"] = _meta(SOURCE_RULE)
        elif len(orgs) > 1:
            data["customer_name"] = orgs[1]
            prov["customer_name"] = _meta(SOURCE_NER, self._entity_confidence(entities, orgs[1], "ORGANIZATION"))
        else:
            persons = [e["text"] for e in entities if e.get("type") == "PERSON"]
            if persons:
                data["customer_name"] = persons[0]
                prov["customer_name"] = _meta(SOURCE_NER, self._entity_confidence(entities, persons[0], "PERSON"))

        return data, prov

    # -- contract ----------------------------------------------------------
    def _extract_contract(self, text: str, entities, pii_entities) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data: Dict[str, Any] = {
            "contract_number": "N/A",
            "parties": [],
            "effective_date": "N/A",
            "expiry_date": "N/A",
            "governing_law": "N/A",
        }
        prov = self._blank(list(data.keys()))

        # Contract number
        c_match = re.search(r"(?:agreement\s*(?:no|#|id)|contract\s*(?:no|#|id))\s*[:.\-]?\s*([A-Z0-9\-_/]+)", text, re.IGNORECASE)
        if c_match:
            data["contract_number"] = c_match.group(1).strip()
            prov["contract_number"] = _meta(SOURCE_RULE)

        # Parties
        orgs_and_persons = [e["text"] for e in entities if e.get("type") in ["ORGANIZATION", "PERSON"]]
        data["parties"] = list(dict.fromkeys(orgs_and_persons))[:4]
        if data["parties"]:
            prov["parties"] = _meta(SOURCE_NER)

        # Effective date
        eff_match = re.search(r"(?:effective\s*date|dated\s*as\s*of|commencement\s*date)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if eff_match:
            data["effective_date"] = eff_match.group(1).strip()
            prov["effective_date"] = _meta(SOURCE_RULE)
        else:
            dates = [p["value"] for p in pii_entities if p.get("type") == "DATE"]
            if dates:
                data["effective_date"] = dates[0]
                prov["effective_date"] = _meta(SOURCE_PII, self._pii_confidence(pii_entities, dates[0], "DATE"))

        # Expiry / Termination date
        exp_match = re.search(r"(?:expiry\s*date|termination\s*date|valid\s*(?:until|through))\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if exp_match:
            data["expiry_date"] = exp_match.group(1).strip()
            prov["expiry_date"] = _meta(SOURCE_RULE)

        # Governing Law
        law_match = re.search(r"(?:governed\s*by|jurisdiction\s*of|laws\s*of)\s*(?:the\s*laws\s*of\s*)?([A-Za-z\s,]+?)(?:\.|\n|;)", text, re.IGNORECASE)
        if law_match:
            data["governing_law"] = law_match.group(1).strip()
            prov["governing_law"] = _meta(SOURCE_RULE)

        return data, prov

    # -- identity ----------------------------------------------------------
    def _extract_identity(self, text: str, entities, pii_entities) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data: Dict[str, Any] = {
            "name": "N/A",
            "document_type": "Identity",
            "document_number": "N/A",
            "date_of_birth": "N/A",
            "gender": "N/A",
            "address": "N/A",
        }
        prov = self._blank(list(data.keys()))
        prov["document_type"] = _meta(SOURCE_DEFAULT)

        # Check for Aadhaar vs PAN
        for pii in pii_entities:
            if pii.get("type") == "AADHAAR":
                data["document_type"] = "Aadhaar Card"
                data["document_number"] = pii.get("masked_value") or pii.get("value")
                prov["document_type"] = _meta(SOURCE_PII, pii.get("confidence"))
                prov["document_number"] = _meta(SOURCE_PII, pii.get("confidence"))
                break
            elif pii.get("type") == "PAN":
                data["document_type"] = "PAN Card"
                data["document_number"] = pii.get("masked_value") or pii.get("value")
                prov["document_type"] = _meta(SOURCE_PII, pii.get("confidence"))
                prov["document_number"] = _meta(SOURCE_PII, pii.get("confidence"))
                break

        # Name
        persons = [e["text"] for e in entities if e.get("type") == "PERSON"]
        name_match = re.search(r"(?:name|holder|cardholder)\s*[:.\-]?\s*([A-Za-z\s]{3,30})", text, re.IGNORECASE)
        if name_match:
            data["name"] = name_match.group(1).strip()
            prov["name"] = _meta(SOURCE_RULE)
        elif persons:
            data["name"] = persons[0]
            prov["name"] = _meta(SOURCE_NER, self._entity_confidence(entities, persons[0], "PERSON"))

        # DOB
        dob_match = re.search(r"(?:dob|date\s*of\s*birth|birth\s*date)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", text, re.IGNORECASE)
        if dob_match:
            data["date_of_birth"] = dob_match.group(1).strip()
            prov["date_of_birth"] = _meta(SOURCE_RULE)
        else:
            dates = [p["value"] for p in pii_entities if p.get("type") == "DATE"]
            if dates:
                data["date_of_birth"] = dates[0]
                prov["date_of_birth"] = _meta(SOURCE_PII, self._pii_confidence(pii_entities, dates[0], "DATE"))

        # Gender
        gender_match = re.search(r"\b(male|female|transgender)\b", text, re.IGNORECASE)
        if gender_match:
            data["gender"] = gender_match.group(1).capitalize()
            prov["gender"] = _meta(SOURCE_RULE)

        # Address
        addr_match = re.search(r"(?:address|residence)\s*[:.\-]?\s*([^\n\r]+(?:\n[^\n\r]+)?)", text, re.IGNORECASE)
        if addr_match:
            data["address"] = addr_match.group(1).strip()
            prov["address"] = _meta(SOURCE_RULE)

        return data, prov

    # -- form --------------------------------------------------------------
    def _extract_form(self, text: str, entities, pii_entities) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data: Dict[str, Any] = {
            "applicant_name": "N/A",
            "email": "N/A",
            "phone": "N/A",
            "dates": [],
            "relevant_fields": {},
        }
        prov = self._blank(list(data.keys()))

        persons = [e["text"] for e in entities if e.get("type") == "PERSON"]
        name_match = re.search(r"(?:applicant\s*name|candidate\s*name|full\s*name)\s*[:.\-]?\s*([A-Za-z\s]{3,30})", text, re.IGNORECASE)
        if name_match:
            data["applicant_name"] = name_match.group(1).strip()
            prov["applicant_name"] = _meta(SOURCE_RULE)
        elif persons:
            data["applicant_name"] = persons[0]
            prov["applicant_name"] = _meta(SOURCE_NER, self._entity_confidence(entities, persons[0], "PERSON"))

        for pii in pii_entities:
            if pii.get("type") == "EMAIL" and data["email"] == "N/A":
                data["email"] = pii.get("masked_value") or pii.get("value")
                prov["email"] = _meta(SOURCE_PII, pii.get("confidence"))
            elif pii.get("type") == "PHONE" and data["phone"] == "N/A":
                data["phone"] = pii.get("masked_value") or pii.get("value")
                prov["phone"] = _meta(SOURCE_PII, pii.get("confidence"))
            elif pii.get("type") == "DATE":
                data["dates"].append(pii.get("value"))
                prov["dates"] = _meta(SOURCE_PII, pii.get("confidence"))

        return data, prov

    # -- generic -----------------------------------------------------------
    def _extract_generic(self, text: str, entities, pii_entities) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        data = {
            "entity_summary": {
                "persons": [e["text"] for e in entities if e.get("type") == "PERSON"][:5],
                "organizations": [e["text"] for e in entities if e.get("type") == "ORGANIZATION"][:5],
                "locations": [e["text"] for e in entities if e.get("type") == "LOCATION"][:5],
            },
            "sensitive_counts": len([p for p in pii_entities if p.get("sensitive")]),
        }
        prov = {
            "entity_summary": _meta(SOURCE_NER) if any(data["entity_summary"].values()) else _meta(SOURCE_NOT_FOUND),
            "sensitive_counts": _meta(SOURCE_DERIVED) if data["sensitive_counts"] else _meta(SOURCE_NOT_FOUND),
        }
        return data, prov


structured_extraction_service = StructuredExtractionService()

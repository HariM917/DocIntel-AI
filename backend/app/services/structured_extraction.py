import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("docintel.extraction")


class StructuredExtractionService:
    """Extracts typed, structured key-value schemas based on document category."""

    def extract(
        self,
        document_type: str,
        text: str,
        entities: List[Dict[str, Any]],
        pii_entities: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        doc_type = document_type.strip().capitalize()
        if doc_type == "Invoice":
            return self._extract_invoice(text, entities, pii_entities)
        elif doc_type == "Contract":
            return self._extract_contract(text, entities, pii_entities)
        elif doc_type == "Identity":
            return self._extract_identity(text, entities, pii_entities)
        elif doc_type in ["Application", "Form"]:
            return self._extract_form(text, entities, pii_entities)
        else:
            return self._extract_generic(text, entities, pii_entities)

    def _extract_invoice(self, text: str, entities: List[Dict[str, Any]], pii_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = {
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

        # 1. Invoice Number
        inv_match = re.search(r"\b(?:invoice|inv)\s*(?:no|number|#|num)?\s*[:.\-#]\s*([A-Z0-9\-_/]+)", text, re.IGNORECASE)
        if not inv_match:
            inv_match = re.search(r"\b(?:invoice|inv)\s+(?:no|number|#|num)\s+([A-Z0-9\-_/]+)", text, re.IGNORECASE)
        if inv_match and inv_match.group(1).upper() not in ["OICE", "DATE", "TAX", "TOTAL"]:
            data["invoice_number"] = inv_match.group(1).strip()
        else:
            for pii in pii_entities:
                if pii.get("type") == "INVOICE_NUMBER":
                    data["invoice_number"] = pii.get("value")
                    break

        # 2. Currency
        if "$" in text or "USD" in text:
            data["currency"] = "USD"
        elif "€" in text or "EUR" in text:
            data["currency"] = "EUR"
        elif "£" in text or "GBP" in text:
            data["currency"] = "GBP"
        elif "₹" in text or "INR" in text or "Rs" in text:
            data["currency"] = "INR"

        # 3. Total Amount
        total_match = re.search(r"\b(?<!sub)(?:grand\s*total|total\s*amount|amount\s*payable|balance\s*due|total)\s*[:.\-]?\s*[₹$€£Rs.]*\s*([0-9,]+\.[0-9]{2}|[0-9,]+)", text, re.IGNORECASE)
        if total_match:
            data["total_amount"] = total_match.group(1).strip()

        # 4. Subtotal
        sub_match = re.search(r"(?:subtotal|sub\s*total|net\s*amount)\s*[:.\-]?\s*[₹$€£Rs.]*\s*([0-9,]+\.[0-9]{2}|[0-9,]+)", text, re.IGNORECASE)
        if sub_match:
            data["subtotal"] = sub_match.group(1).strip()

        # 5. Tax / GST / VAT
        tax_match = re.search(r"(?:tax|gst|vat|cgst\s*\+\s*sgst|igst)\s*[:.\-]?\s*[₹$€£Rs.]*\s*([0-9,]+\.[0-9]{2}|[0-9,]+)", text, re.IGNORECASE)
        if tax_match:
            data["tax"] = tax_match.group(1).strip()

        # 6. Dates
        dates = [p["value"] for p in pii_entities if p.get("type") == "DATE"]
        inv_date_match = re.search(r"(?:invoice\s*date|bill\s*date|date)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if inv_date_match:
            data["invoice_date"] = inv_date_match.group(1).strip()
        elif dates:
            data["invoice_date"] = dates[0]

        due_date_match = re.search(r"(?:due\s*date|payment\s*due)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if due_date_match:
            data["due_date"] = due_date_match.group(1).strip()
        elif len(dates) > 1 and data["invoice_date"] != dates[1]:
            data["due_date"] = dates[1]

        # 7. Vendor Name (often first Organization entity or top of document)
        orgs = [e["text"] for e in entities if e.get("type") == "ORGANIZATION"]
        vendor_match = re.search(r"(?:vendor|from|billed\s*by|supplier)\s*[:.\-]?\s*([A-Za-z0-9&.\s]{3,35})", text, re.IGNORECASE)
        if vendor_match:
            data["vendor_name"] = vendor_match.group(1).strip()
        elif orgs:
            data["vendor_name"] = orgs[0]

        # 8. Customer / Client Name
        cust_match = re.search(r"(?:bill\s*to|customer|client|sold\s*to)\s*[:.\-]?\s*([A-Za-z0-9&.\s]{3,35})", text, re.IGNORECASE)
        if cust_match:
            data["customer_name"] = cust_match.group(1).strip()
        elif len(orgs) > 1:
            data["customer_name"] = orgs[1]
        else:
            persons = [e["text"] for e in entities if e.get("type") == "PERSON"]
            if persons:
                data["customer_name"] = persons[0]

        return data

    def _extract_contract(self, text: str, entities: List[Dict[str, Any]], pii_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = {
            "contract_number": "N/A",
            "parties": [],
            "effective_date": "N/A",
            "expiry_date": "N/A",
            "governing_law": "N/A",
        }

        # Contract number
        c_match = re.search(r"(?:agreement\s*(?:no|#|id)|contract\s*(?:no|#|id))\s*[:.\-]?\s*([A-Z0-9\-_/]+)", text, re.IGNORECASE)
        if c_match:
            data["contract_number"] = c_match.group(1).strip()

        # Parties
        orgs_and_persons = [e["text"] for e in entities if e.get("type") in ["ORGANIZATION", "PERSON"]]
        data["parties"] = list(dict.fromkeys(orgs_and_persons))[:4]

        # Effective date
        eff_match = re.search(r"(?:effective\s*date|dated\s*as\s*of|commencement\s*date)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if eff_match:
            data["effective_date"] = eff_match.group(1).strip()
        else:
            dates = [p["value"] for p in pii_entities if p.get("type") == "DATE"]
            if dates:
                data["effective_date"] = dates[0]

        # Expiry / Termination date
        exp_match = re.search(r"(?:expiry\s*date|termination\s*date|valid\s*(?:until|through))\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}|[A-Za-z]+\s+[0-9]{1,2},?\s+[0-9]{4})", text, re.IGNORECASE)
        if exp_match:
            data["expiry_date"] = exp_match.group(1).strip()

        # Governing Law
        law_match = re.search(r"(?:governed\s*by|jurisdiction\s*of|laws\s*of)\s*(?:the\s*laws\s*of\s*)?([A-Za-z\s,]+?)(?:\.|\n|;)", text, re.IGNORECASE)
        if law_match:
            data["governing_law"] = law_match.group(1).strip()

        return data

    def _extract_identity(self, text: str, entities: List[Dict[str, Any]], pii_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = {
            "name": "N/A",
            "document_type": "Identity",
            "document_number": "N/A",
            "date_of_birth": "N/A",
            "gender": "N/A",
            "address": "N/A",
        }

        # Check for Aadhaar vs PAN
        for pii in pii_entities:
            if pii.get("type") == "AADHAAR":
                data["document_type"] = "Aadhaar Card"
                data["document_number"] = pii.get("masked_value") or pii.get("value")
                break
            elif pii.get("type") == "PAN":
                data["document_type"] = "PAN Card"
                data["document_number"] = pii.get("masked_value") or pii.get("value")
                break

        # Name
        persons = [e["text"] for e in entities if e.get("type") == "PERSON"]
        name_match = re.search(r"(?:name|holder|cardholder)\s*[:.\-]?\s*([A-Za-z\s]{3,30})", text, re.IGNORECASE)
        if name_match:
            data["name"] = name_match.group(1).strip()
        elif persons:
            data["name"] = persons[0]

        # DOB
        dob_match = re.search(r"(?:dob|date\s*of\s*birth|birth\s*date)\s*[:.\-]?\s*([0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4})", text, re.IGNORECASE)
        if dob_match:
            data["date_of_birth"] = dob_match.group(1).strip()
        else:
            dates = [p["value"] for p in pii_entities if p.get("type") == "DATE"]
            if dates:
                data["date_of_birth"] = dates[0]

        # Gender
        gender_match = re.search(r"\b(male|female|transgender)\b", text, re.IGNORECASE)
        if gender_match:
            data["gender"] = gender_match.group(1).capitalize()

        # Address
        addr_match = re.search(r"(?:address|residence)\s*[:.\-]?\s*([^\n\r]+(?:\n[^\n\r]+)?)", text, re.IGNORECASE)
        if addr_match:
            data["address"] = addr_match.group(1).strip()

        return data

    def _extract_form(self, text: str, entities: List[Dict[str, Any]], pii_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = {
            "applicant_name": "N/A",
            "email": "N/A",
            "phone": "N/A",
            "dates": [],
            "relevant_fields": {},
        }

        persons = [e["text"] for e in entities if e.get("type") == "PERSON"]
        name_match = re.search(r"(?:applicant\s*name|candidate\s*name|full\s*name)\s*[:.\-]?\s*([A-Za-z\s]{3,30})", text, re.IGNORECASE)
        if name_match:
            data["applicant_name"] = name_match.group(1).strip()
        elif persons:
            data["applicant_name"] = persons[0]

        for pii in pii_entities:
            if pii.get("type") == "EMAIL" and data["email"] == "N/A":
                data["email"] = pii.get("masked_value") or pii.get("value")
            elif pii.get("type") == "PHONE" and data["phone"] == "N/A":
                data["phone"] = pii.get("masked_value") or pii.get("value")
            elif pii.get("type") == "DATE":
                data["dates"].append(pii.get("value"))

        return data

    def _extract_generic(self, text: str, entities: List[Dict[str, Any]], pii_entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "entity_summary": {
                "persons": [e["text"] for e in entities if e.get("type") == "PERSON"][:5],
                "organizations": [e["text"] for e in entities if e.get("type") == "ORGANIZATION"][:5],
                "locations": [e["text"] for e in entities if e.get("type") == "LOCATION"][:5],
            },
            "sensitive_counts": len([p for p in pii_entities if p.get("sensitive")]),
        }


structured_extraction_service = StructuredExtractionService()

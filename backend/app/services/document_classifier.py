import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger("docintel.classifier")


class DocumentClassifier:
    """Classifies document texts into Invoice, Contract, Identity, Application, Form, or Other

    Uses weighted multi-signal keyword & contextual pattern matching with extensible ML hook.
    """

    CATEGORIES = {
        "Invoice": {
            "keywords": [
                "invoice", "tax invoice", "bill to", "ship to", "subtotal", "total amount",
                "gstin", "vat", "balance due", "payment terms", "due date", "po number",
                "hsn", "sac", "unit price", "line total", "remit to", "billed to", "qty"
            ],
            "patterns": [
                r"inv[-_ ]?[0-9]{3,}",
                r"invoice\s*(?:no|number|#)?\s*[:.\-]?\s*[A-Z0-9\-_/]+",
                r"total\s*amount\s*[:.\-]?\s*[₹$€£]?\s*[0-9,.]+",
                r"due\s*date\s*[:.\-]?\s*[0-9]{1,2}[/-][0-9]{1,2}[/-][0-9]{2,4}",
            ],
            "weight": 1.2,
        },
        "Contract": {
            "keywords": [
                "agreement", "contract", "parties", "hereby agreed", "terms and conditions",
                "indemnification", "confidentiality", "non-disclosure", "jurisdiction",
                "in witness whereof", "effective date", "termination", "governing law",
                "intellectual property", "covenant", "severability", "arbitration"
            ],
            "patterns": [
                r"by\s+and\s+between",
                r"whereas\s*,",
                r"now\s*,?\s*therefore",
                r"section\s+[0-9]+(?:\.[0-9]+)*\s+[A-Z]",
            ],
            "weight": 1.1,
        },
        "Identity": {
            "keywords": [
                "government of india", "aadhaar", "unique identification authority",
                "income tax department", "permanent account number", "pan card",
                "election commission", "voter id", "driving licence", "passport",
                "date of birth", "dob", "father's name", "enrolment no", "vid",
                "republic of india"
            ],
            "patterns": [
                r"[0-9]{4}\s+[0-9]{4}\s+[0-9]{4}",  # Aadhaar
                r"[A-Z]{5}[0-9]{4}[A-Z]",            # PAN
                r"male|female|transgender",
                r"dob\s*[:.\-]?\s*[0-9]{2}[/-][0-9]{2}[/-][0-9]{4}",
            ],
            "weight": 1.3,
        },
        "Application": {
            "keywords": [
                "application form", "applicant name", "job application", "position applied",
                "employment history", "educational qualifications", "curriculum vitae",
                "declaration", "signature of applicant", "work experience", "references"
            ],
            "patterns": [
                r"applied\s+for",
                r"years\s+of\s+experience",
                r"highest\s+qualification",
            ],
            "weight": 1.0,
        },
        "Form": {
            "keywords": [
                "registration form", "survey form", "feedback form", "enrolment form",
                "admission form", "please fill", "tick appropriate", "official use only",
                "declaration", "check box", "signature"
            ],
            "patterns": [
                r"\[\s*\]|\(\s*\)|form\s*(?:no|number)",
                r"for\s+office\s+use\s+only",
            ],
            "weight": 0.9,
        },
    }

    def classify(self, text: str) -> Dict[str, Any]:
        """Classifies text into categories and computes a confidence score."""
        if not text or len(text.strip()) < 10:
            return {"document_type": "Other", "confidence": 0.50}

        text_lower = text.lower()
        scores: Dict[str, float] = {}

        for category, config in self.CATEGORIES.items():
            category_score = 0.0
            # 1. Check Keywords
            for kw in config["keywords"]:
                if kw in text_lower:
                    # Longer keyword matches provide stronger signal
                    category_score += len(kw.split()) * 1.5

            # 2. Check Regex Patterns
            for pattern in config["patterns"]:
                matches = re.findall(pattern, text, re.IGNORECASE)
                category_score += len(matches) * 2.5

            scores[category] = category_score * config["weight"]

        best_category = max(scores, key=scores.get)
        best_score = scores[best_category]

        if best_score < 3.0:
            return {"document_type": "Other", "confidence": 0.55}

        # Calculate normalized confidence score
        # Using a sigmoid-like scaling
        confidence = min(0.98, max(0.65, round(best_score / (best_score + 10.0) + 0.35, 2)))
        return {
            "document_type": best_category,
            "confidence": float(confidence),
            "signals": {k: round(v, 2) for k, v in scores.items() if v > 0},
        }


document_classifier = DocumentClassifier()

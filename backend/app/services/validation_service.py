import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


class ValidationService:
    """Validates extracted entity formats and checksum algorithms (Verhoeff, Luhn, etc.).

    Phase 3 adds field-level format checks (date, URL, currency, numeric, ID)
    and cross-field consistency checks. Validation never discards a value; it
    only classifies it as valid / invalid / uncertain.
    """

    # Accepted date formats, tried in order. Impossible dates (e.g. 99/99/9999)
    # fail every format and are therefore reported as invalid.
    DATE_FORMATS = (
        "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d",
        "%d/%m/%y", "%d-%m-%y", "%m/%d/%Y",
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
    )

    # Verhoeff algorithm multiplication table
    VERHOEFF_D = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
    ]

    # Verhoeff permutation table
    VERHOEFF_P = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]
    ]

    # Verhoeff inverse table
    VERHOEFF_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]

    @classmethod
    def validate_verhoeff(cls, num_str: str) -> bool:
        """Validates a number using the Verhoeff algorithm."""
        digits = re.sub(r"\D", "", num_str)
        if not digits:
            return False
        c = 0
        for i, digit in enumerate(reversed(digits)):
            c = cls.VERHOEFF_D[c][cls.VERHOEFF_P[i % 8][int(digit)]]
        return c == 0

    @classmethod
    def validate_luhn(cls, card_number: str) -> bool:
        """Validates credit/debit card numbers using the Luhn checksum (MOD 10)."""
        digits = re.sub(r"\D", "", card_number)
        if not (13 <= len(digits) <= 19):
            return False
        total = 0
        reverse_digits = digits[::-1]
        for i, char in enumerate(reverse_digits):
            n = int(char)
            if i % 2 == 1:
                n *= 2
                if n > 9:
                    n -= 9
            total += n
        return total % 10 == 0

    @classmethod
    def validate_aadhaar(cls, aadhaar_str: str) -> Tuple[bool, str]:
        """Validates Indian Aadhaar format (12 digits, cannot start with 0 or 1)."""
        clean = re.sub(r"\D", "", aadhaar_str)
        if len(clean) != 12:
            return False, "Aadhaar must be exactly 12 digits"
        if clean[0] in ["0", "1"]:
            return False, "Aadhaar cannot start with 0 or 1"
        # Check Verhoeff if strict checksum is desired, or format validation
        is_verhoeff = cls.validate_verhoeff(clean)
        return True, "Valid Aadhaar format" if not is_verhoeff else "Valid Aadhaar (Verhoeff verified)"

    @classmethod
    def validate_pan(cls, pan_str: str) -> Tuple[bool, str]:
        """Validates Indian Permanent Account Number (PAN): 5 letters + 4 digits + 1 letter."""
        clean = pan_str.strip().upper()
        if not re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", clean):
            return False, "PAN must follow format [A-Z]{5}[0-9]{4}[A-Z]"
        # 4th character represents taxpayer status
        valid_status = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "L", "P", "T"]
        if clean[3] not in valid_status:
            return False, f"Invalid 4th character '{clean[3]}' in PAN"
        return True, "Valid PAN"

    @classmethod
    def validate_email(cls, email: str) -> Tuple[bool, str]:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if re.match(pattern, email.strip()):
            return True, "Valid Email"
        return False, "Invalid Email format"

    @classmethod
    def validate_phone(cls, phone_str: str) -> Tuple[bool, str]:
        clean = re.sub(r"\D", "", phone_str)
        # Indian 10-digit mobile (or with country code 91)
        if len(clean) == 12 and clean.startswith("91"):
            clean = clean[2:]
        if len(clean) == 10 and clean[0] in ["6", "7", "8", "9"]:
            return True, "Valid 10-digit Indian Mobile"
        elif 7 <= len(clean) <= 15:
            return True, "Valid International Phone"
        return False, "Invalid Phone format"

    @classmethod
    def validate_bank_account(cls, acc_str: str) -> Tuple[bool, str]:
        clean = re.sub(r"\D", "", acc_str)
        if 9 <= len(clean) <= 18:
            return True, "Valid Bank Account length"
        return False, "Bank Account should be 9 to 18 digits"

    # ------------------------------------------------------------------
    # Phase 3 — field-level format validation (Step 12)
    # ------------------------------------------------------------------
    @classmethod
    def validate_date(cls, date_str: str) -> Tuple[bool, str]:
        """Validates a date, rejecting impossible values such as 99/99/9999."""
        s = (date_str or "").strip()
        if not s:
            return False, "Empty date"
        for fmt in cls.DATE_FORMATS:
            try:
                datetime.strptime(s, fmt)
                return True, "Valid date"
            except ValueError:
                continue
        return False, "Unrecognized or impossible date"

    @classmethod
    def validate_url(cls, url_str: str) -> Tuple[bool, str]:
        s = (url_str or "").strip()
        if re.fullmatch(r"https?://[^\s/]+(?:\.[^\s/]+)+(?:/[^\s]*)?", s, re.IGNORECASE):
            return True, "Valid URL"
        return False, "Invalid URL"

    @classmethod
    def validate_currency(cls, value: str) -> Tuple[bool, str]:
        """Validates a monetary amount with an optional symbol/code."""
        s = (value or "").strip()
        if re.fullmatch(
            r"[₹$€£]?\s?-?[0-9][0-9,]*(?:\.[0-9]{1,2})?\s?(?:INR|USD|EUR|GBP|Rs\.?)?",
            s,
            re.IGNORECASE,
        ):
            return True, "Valid currency amount"
        return False, "Invalid currency amount"

    @classmethod
    def validate_numeric(cls, value: str) -> Tuple[bool, str]:
        s = re.sub(r"[,\s]", "", (value or "").strip())
        if not s:
            return False, "Empty numeric"
        try:
            float(s)
            return True, "Valid numeric"
        except ValueError:
            return False, "Invalid numeric"

    @classmethod
    def validate_identifier(cls, value: str) -> Tuple[bool, str]:
        s = (value or "").strip()
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_/]{2,30}", s):
            return True, "Valid identifier"
        return False, "Invalid identifier"

    @classmethod
    def classify_field(cls, field_type: str, value: Any) -> str:
        """Classifies a field value as ``valid`` / ``invalid`` / ``uncertain``.

        Unknown field types are reported as ``uncertain`` rather than guessed.
        Compound names produced by the extraction schemas (``invoice_date``,
        ``total_amount``, ``customer_email``) are resolved by token so they are
        validated when a confident match exists.
        """
        if value in (None, "", "N/A", "n/a", "NA"):
            return "uncertain"
        ft = (field_type or "").lower()
        validators = {
            "email": cls.validate_email,
            "phone": cls.validate_phone,
            "date": cls.validate_date,
            "url": cls.validate_url,
            "currency": cls.validate_currency,
            "amount": cls.validate_currency,
            "total": cls.validate_currency,
            "numeric": cls.validate_numeric,
            "number": cls.validate_numeric,
            "identifier": cls.validate_identifier,
            "id": cls.validate_identifier,
        }
        fn = validators.get(ft)
        if fn is None:
            # Resolve compound names by their trailing token(s), longest first,
            # so "invoice_date" -> date and "total_amount" -> amount.
            tokens = [t for t in re.split(r"[^a-z]+", ft) if t]
            for token in reversed(tokens):
                if token in validators:
                    fn = validators[token]
                    break
        if fn is None:
            return "uncertain"
        ok, _ = fn(str(value))
        return "valid" if ok else "invalid"

    # ------------------------------------------------------------------
    # Phase 3 — cross-field consistency checks (Step 13)
    # ------------------------------------------------------------------
    @classmethod
    def cross_field_validate(cls, document_type: str, structured_data: Dict[str, Any]) -> List[Dict[str, str]]:
        """Returns validation warnings kept separate from extraction results.

        Only domain rules justified by the document type are applied.
        """
        warnings: List[Dict[str, str]] = []
        if not structured_data:
            return warnings
        dt = (document_type or "").strip().lower()

        if dt == "invoice":
            subtotal = cls._to_number(structured_data.get("subtotal"))
            tax = cls._to_number(structured_data.get("tax"))
            total = cls._to_number(structured_data.get("total_amount"))
            if subtotal is not None and tax is not None and total is not None:
                tolerance = max(1.0, 0.02 * abs(total))
                if abs((subtotal + tax) - total) > tolerance:
                    warnings.append({
                        "field": "total_amount",
                        "code": "CROSS_FIELD_MISMATCH",
                        "message": "subtotal + tax does not equal total_amount.",
                    })
            for field in ("invoice_date", "due_date"):
                val = structured_data.get(field)
                if val and val != "N/A":
                    ok, _ = cls.validate_date(str(val))
                    if not ok:
                        warnings.append({
                            "field": field,
                            "code": "INVALID_DATE",
                            "message": f"'{field}' is not a valid date.",
                        })

        elif dt == "contract":
            effective = cls._parse_date(structured_data.get("effective_date"))
            expiry = cls._parse_date(structured_data.get("expiry_date"))
            if effective and expiry and expiry < effective:
                warnings.append({
                    "field": "expiry_date",
                    "code": "DATE_ORDER",
                    "message": "expiry_date precedes effective_date.",
                })

        return warnings

    @staticmethod
    def _to_number(value: Any) -> Optional[float]:
        if value is None:
            return None
        s = re.sub(r"[^0-9.\-]", "", str(value))
        if not s or s in ("-", ".", "-."):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    @classmethod
    def _parse_date(cls, value: Any) -> Optional[datetime]:
        s = (str(value) if value is not None else "").strip()
        if not s or s == "N/A":
            return None
        for fmt in cls.DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None


validation_service = ValidationService()

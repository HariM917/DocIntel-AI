import re
from typing import Tuple


class ValidationService:
    """Validates extracted entity formats and checksum algorithms (Verhoeff, Luhn, etc.)."""

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


validation_service = ValidationService()

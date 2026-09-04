import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("docintel.redaction")


class RedactionService:
    """Masks sensitive values and redacts text based on active security rules."""

    @staticmethod
    def mask_email(email: str) -> str:
        parts = email.split("@")
        if len(parts) != 2:
            return "*****"
        name, domain = parts
        if len(name) <= 1:
            masked_name = name + "***"
        else:
            masked_name = name[0] + "***" + (name[-1] if len(name) > 2 else "")
        return f"{masked_name}@{domain}"

    @staticmethod
    def mask_aadhaar(aadhaar: str) -> str:
        clean = re.sub(r"\D", "", aadhaar)
        if len(clean) >= 4:
            last4 = clean[-4:]
            return f"XXXX XXXX {last4}"
        return "XXXX XXXX XXXX"

    @staticmethod
    def mask_pan(pan: str) -> str:
        clean = pan.strip()
        if len(clean) == 10:
            return f"XXXXX{clean[5:]}"
        return "XXXXXXXXXX"

    @staticmethod
    def mask_phone(phone: str) -> str:
        clean = re.sub(r"\D", "", phone)
        if len(clean) >= 4:
            last4 = clean[-4:]
            stars = "*" * (len(clean) - 4)
            return f"{stars}{last4}"
        return "******"

    @staticmethod
    def mask_credit_card(card: str) -> str:
        clean = re.sub(r"\D", "", card)
        if len(clean) >= 4:
            last4 = clean[-4:]
            return f"XXXX-XXXX-XXXX-{last4}"
        return "XXXX-XXXX-XXXX-XXXX"

    @staticmethod
    def mask_bank_account(acc: str) -> str:
        clean = re.sub(r"\D", "", acc)
        if len(clean) >= 4:
            last4 = clean[-4:]
            stars = "*" * (len(clean) - 4)
            return f"{stars}{last4}"
        return "********"

    @staticmethod
    def mask_generic(val: str) -> str:
        if len(val) <= 2:
            return "**"
        return val[0] + ("*" * (len(val) - 2)) + val[-1]

    def get_masked_value(self, entity_type: str, value: str) -> str:
        """Returns the masked version of a sensitive value according to its entity type."""
        t = entity_type.upper()
        if t == "EMAIL":
            return self.mask_email(value)
        elif t == "AADHAAR":
            return self.mask_aadhaar(value)
        elif t == "PAN":
            return self.mask_pan(value)
        elif t == "PHONE":
            return self.mask_phone(value)
        elif t in ["CREDIT_CARD", "CARD"]:
            return self.mask_credit_card(value)
        elif t in ["BANK_ACCOUNT", "ACCOUNT"]:
            return self.mask_bank_account(value)
        elif t == "PERSON":
            # Mask middle of person name (e.g. Rahul Sharma -> R**** S****)
            words = value.split()
            return " ".join(w[0] + ("*" * max(1, len(w) - 1)) for w in words if w)
        return self.mask_generic(value)

    def redact_document(
        self,
        text: str,
        pii_entities: List[Dict[str, Any]],
        active_rules: Optional[Dict[str, bool]] = None
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Generates redacted text and updates entities with their masked values.

        Respects active security rules if provided.
        """
        active_rules = active_rules or {}
        redacted_text = text
        processed_entities = []

        # Sort entities by value length descending to avoid partial substring collisions
        sorted_entities = sorted(pii_entities, key=lambda x: len(x.get("value", "")), reverse=True)

        for ent in sorted_entities:
            ent_copy = dict(ent)
            ent_type = ent_copy.get("type", "")
            raw_value = ent_copy.get("value", "")

            # Check if this rule is enabled (default is enabled for sensitive types)
            is_enabled = active_rules.get(ent_type, ent_copy.get("sensitive", False))

            if is_enabled and ent_copy.get("sensitive", False):
                masked = self.get_masked_value(ent_type, raw_value)
                ent_copy["masked_value"] = masked
                # Replace in redacted text using exact word boundary or literal replacement
                if raw_value in redacted_text:
                    redacted_text = redacted_text.replace(raw_value, masked)
            else:
                ent_copy["masked_value"] = raw_value

            processed_entities.append(ent_copy)

        # Restore original order of entities
        processed_entities.sort(key=lambda x: x.get("start") or 0)
        return redacted_text, processed_entities


redaction_service = RedactionService()

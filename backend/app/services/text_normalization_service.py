"""Text normalization stage (Phase 3, Steps 3 & 4).

Normalizes raw OCR output *without* destroying meaningful layout information or
altering semantically important tokens. Normalization is deliberately
conservative: it never rewrites digits, dates, emails, phone numbers, currency
or identifiers -- it only removes noise introduced by OCR.

The original OCR text is always preserved separately (``original_text``); the
normalized form is what downstream stages consume.
"""
import logging
import re
import unicodedata
from collections import Counter
from typing import Any, Dict, List

logger = logging.getLogger("docintel.normalization")

# Pages produced by the OCR service are separated by this marker.
PAGE_BREAK = "\n\n--- Page Break ---\n\n"

# Control characters that OCR engines occasionally emit, excluding \n and \t.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Two or more spaces/tabs inside a line (indentation is preserved by only
# collapsing the *interior* runs, which never start at column 0).
_INTERIOR_SPACE = re.compile(r"(?<=\S)[ \t]{2,}")
# Three or more consecutive newlines (excessive blank lines).
_EXCESS_NEWLINES = re.compile(r"\n{3,}")
# Word broken across a line by a hyphen: "exam-\nple" -> "example".
_HYPHEN_LINEBREAK = re.compile(r"(\w)-\n(\w)")
# Repeated punctuation runs produced by noise: "!!!!!!" -> "!!!".
_REPEAT_PUNCT = re.compile(r"([!?.,;:])\1{2,}")
# A very short line is a candidate header/footer (avoids removing real content).
_MAX_HEADER_LEN = 80


class TextNormalizationService:
    """Produces ``normalized_text`` from raw OCR text with safe, documented rules."""

    def normalize(self, text: str) -> Dict[str, Any]:
        original = text or ""
        warnings: List[str] = []

        if not original.strip():
            return {
                "normalized_text": "",
                "original_text": original,
                "empty": True,
                "warnings": ["OCR produced no usable text."],
                "stats": {"input_chars": len(original), "output_chars": 0, "pages": 0},
            }

        work = original

        # 1. Unicode normalization (compatibility form: NFKC).
        work = unicodedata.normalize("NFKC", work)

        # 2. Unify line endings.
        work = work.replace("\r\n", "\n").replace("\r", "\n")

        # 3. Strip control characters that are not whitespace we rely on.
        work = _CONTROL_CHARS.sub("", work)

        # 4. Re-join words broken across a line by a hyphen.
        work = _HYPHEN_LINEBREAK.sub(r"\1\2", work)

        # 5. Remove repeated page headers/footers (conservative).
        work, removed = self._strip_repeated_headers_footers(work)
        if removed:
            warnings.append(f"Removed {removed} repeated header/footer line(s).")

        # 6. Collapse interior whitespace runs while preserving line structure
        #    and leading indentation.
        work = "\n".join(
            _INTERIOR_SPACE.sub(" ", line).rstrip() for line in work.split("\n")
        )

        # 7. Collapse excessive blank lines to a single paragraph break.
        work = _EXCESS_NEWLINES.sub("\n\n", work)

        # 8. Tame repeated punctuation artifacts.
        work = _REPEAT_PUNCT.sub(r"\1\1", work)

        work = work.strip()

        if not work:
            warnings.append("Text became empty after normalization.")

        return {
            "normalized_text": work,
            "original_text": original,
            "empty": not bool(work.strip()),
            "warnings": warnings,
            "stats": {
                "input_chars": len(original),
                "output_chars": len(work),
                "pages": original.count(PAGE_BREAK) + 1,
            },
        }

    def _strip_repeated_headers_footers(self, text: str) -> tuple:
        """Removes lines that repeat identically as the first/last line of pages.

        Only short lines that appear as the first (or last) line of **two or
        more** pages are treated as headers/footers, and only from pages after
        the first -- conservative by design so unique content is never deleted.
        """
        pages = text.split(PAGE_BREAK)
        if len(pages) < 2:
            return text, 0

        page_lines = [p.split("\n") for p in pages]

        def _first_nonempty(lines: List[str]):
            for ln in lines:
                if ln.strip():
                    return ln.strip()
            return None

        def _last_nonempty(lines: List[str]):
            for ln in reversed(lines):
                if ln.strip():
                    return ln.strip()
            return None

        first_counts = Counter(
            f for f in (_first_nonempty(pl) for pl in page_lines) if f
        )
        last_counts = Counter(
            l for l in (_last_nonempty(pl) for pl in page_lines) if l
        )

        repeated_headers = {
            h for h, count in first_counts.items()
            if count >= 2 and len(h) <= _MAX_HEADER_LEN
        }
        repeated_footers = {
            f for f, count in last_counts.items()
            if count >= 2 and len(f) <= _MAX_HEADER_LEN
        }

        removed = 0
        for idx in range(1, len(page_lines)):
            lines = page_lines[idx]
            # Remove leading repeated header lines.
            while lines and lines[0].strip() in repeated_headers:
                lines.pop(0)
                removed += 1
            # Remove trailing repeated footer lines.
            while lines and lines[-1].strip() in repeated_footers:
                lines.pop()
                removed += 1

        return PAGE_BREAK.join("\n".join(lines) for lines in page_lines), removed


text_normalization_service = TextNormalizationService()

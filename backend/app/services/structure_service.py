"""Document structure detection (Phase 3, Step 5).

A deliberately *practical* structure analyzer for the document formats this
application supports (invoices, contracts, identity documents, forms, resumes).
It is not a universal parser: it detects the structures that downstream stages
can actually use.

Detected structures:
* key-value fields ("Name: Hari M", "Invoice No = INV-1")
* headings / sections
* bullet & numbered lists
* tables (pipe-delimited or column-aligned text)
"""
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger("docintel.structure")

_KEY_VALUE = re.compile(r"^\s{0,4}(?P<key>[A-Za-z][A-Za-z0-9 ./_\-()]{0,40}?)\s*[:=]\s*(?P<value>\S.*)$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d{1,3}[.)])\s+\S")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_COLUMN_ALIGNED = re.compile(r"\S {2,}\S {2,}\S")
_HEADING = re.compile(r"^[A-Z][A-Za-z0-9 ,&/'\-()]{2,79}$")
_SENTENCE_END = re.compile(r"[.:;!?,]$")


class StructureService:
    """Extracts structure metadata from normalized document text."""

    def analyze(self, text: str) -> Dict[str, Any]:
        if not text or not text.strip():
            return {
                "headings": [],
                "sections": [],
                "key_value_fields": {},
                "lists": [],
                "tables": [],
                "paragraph_count": 0,
            }

        lines = text.split("\n")
        headings: List[Dict[str, Any]] = []
        sections: List[Dict[str, Any]] = []
        key_values: Dict[str, str] = {}
        lists: List[Dict[str, Any]] = []
        tables: List[Dict[str, Any]] = []

        current_list: List[str] = []
        current_table: List[str] = []
        current_section: str = ""

        def _flush_list() -> None:
            if len(current_list) >= 2:
                lists.append({"section": current_section, "items": list(current_list)})
            current_list.clear()

        def _flush_table() -> None:
            if len(current_table) >= 2:
                tables.append({"section": current_section, "rows": list(current_table)})
            current_table.clear()

        for index, raw_line in enumerate(lines):
            line = raw_line.rstrip()
            stripped = line.strip()

            if not stripped:
                _flush_list()
                _flush_table()
                continue

            if _LIST_ITEM.match(line):
                _flush_table()
                current_list.append(stripped)
                continue

            if _TABLE_ROW.match(line) or _COLUMN_ALIGNED.search(line):
                _flush_list()
                current_table.append(stripped)
                continue

            _flush_list()
            _flush_table()

            kv = _KEY_VALUE.match(line)
            if kv:
                key = kv.group("key").strip()
                value = kv.group("value").strip()
                # Guard against sentence-like lines that merely contain a colon.
                if key and value and key.lower() not in key_values:
                    key_values[key] = value
                continue

            if self._looks_like_heading(stripped):
                headings.append({"text": stripped, "line": index})
                current_section = stripped
                sections.append({"title": stripped, "line": index})

        _flush_list()
        _flush_table()

        paragraph_count = len([b for b in re.split(r"\n\s*\n", text) if b.strip()])

        return {
            "headings": headings,
            "sections": sections,
            "key_value_fields": key_values,
            "lists": lists,
            "tables": tables,
            "paragraph_count": paragraph_count,
        }

    @staticmethod
    def _looks_like_heading(line: str) -> bool:
        if len(line) > 79 or _SENTENCE_END.search(line):
            return False
        if _KEY_VALUE.match(line):
            return False
        if ":" in line:
            return False
        if not _HEADING.match(line):
            return False
        # Require a heading-like signal: all-caps or title-case.
        return line.isupper() or line.istitle()


structure_service = StructureService()

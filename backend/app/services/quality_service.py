"""Document-processing quality assessment (Phase 3, Steps 14 & 15).

This is **pipeline quality**, not model accuracy. It measures how well the
document was *processed* -- whether text was readable, whether fields were
found, whether validation passed -- and is explicitly not a scientifically
calibrated accuracy metric.

Documented formula (weights sum to 1.0):

    score = 0.35 * ocr_component
          + 0.25 * text_component
          + 0.15 * entity_component
          + 0.25 * coverage_component
          - penalty

where:
    ocr_component      = mean OCR confidence (0.0-1.0)
    text_component     = min(1.0, text_length / 800)   # ~one page of text
    entity_component   = min(1.0, entity_count / 5)
    coverage_component = fraction of structured fields with a real value
    penalty            = min(0.30, 0.05 * validation_failures)

Levels:
    excellent >= 0.90
    good      >= 0.75
    fair      >= 0.50
    poor      <  0.50
"""
import logging
from typing import Any, Dict, List

logger = logging.getLogger("docintel.quality")

QUALITY_THRESHOLDS = {
    "excellent": 0.90,
    "good": 0.75,
    "fair": 0.50,
}

_EMPTY_TOKENS = {"", "n/a", "na", "none", "null", "-"}


def quality_level(score: float) -> str:
    if score >= QUALITY_THRESHOLDS["excellent"]:
        return "excellent"
    if score >= QUALITY_THRESHOLDS["good"]:
        return "good"
    if score >= QUALITY_THRESHOLDS["fair"]:
        return "fair"
    return "poor"


class QualityService:
    """Computes a `document_quality_score` and human-readable issues."""

    def assess(
        self,
        *,
        ocr_confidence: float,
        text_length: int,
        entity_count: int,
        structured_data: Dict[str, Any],
        validation_failures: int,
        ocr_empty: bool = False,
        pages: int = 1,
    ) -> Dict[str, Any]:
        issues: List[str] = []

        ocr_component = max(0.0, min(1.0, float(ocr_confidence or 0.0)))
        text_component = min(1.0, text_length / 800.0)
        entity_component = min(1.0, entity_count / 5.0)
        coverage_component = self._field_coverage(structured_data)

        if ocr_empty or text_length == 0:
            issues.append("No usable text could be read from the document.")
            ocr_component = 0.0
        elif ocr_component < 0.60:
            issues.append("Low OCR confidence detected.")

        if pages > 1 and ocr_confidence < 0.70:
            issues.append(f"Low OCR confidence across {pages} pages.")

        if entity_component < 0.4:
            issues.append("Few named entities were extracted.")

        if coverage_component < 0.5:
            issues.append("Low structured field coverage.")

        if validation_failures:
            issues.append(f"{validation_failures} field(s) failed validation.")

        penalty = min(0.30, 0.05 * validation_failures)

        score = (
            0.35 * ocr_component
            + 0.25 * text_component
            + 0.15 * entity_component
            + 0.25 * coverage_component
            - penalty
        )
        score = round(max(0.0, min(1.0, score)), 4)

        return {
            "score": score,
            "level": quality_level(score),
            "issues": issues,
            "factors": {
                "ocr_confidence": round(ocr_component, 4),
                "text_length": text_length,
                "entity_count": entity_count,
                "field_coverage": round(coverage_component, 4),
                "validation_failures": validation_failures,
            },
        }

    @staticmethod
    def _field_coverage(structured_data: Dict[str, Any]) -> float:
        if not structured_data:
            return 0.0
        values = [
            v
            for v in structured_data.values()
            if not isinstance(v, (list, dict))
        ]
        if not values:
            return 0.0
        filled = sum(
            1
            for v in values
            if str(v).strip().lower() not in _EMPTY_TOKENS
        )
        return filled / len(values)


quality_service = QualityService()

import pytest
from app.services.ner_service import ner_service, LABEL_MAPPING


def test_ner_label_mapping():
    assert LABEL_MAPPING.get("PER") == "PERSON"
    assert LABEL_MAPPING.get("ORG") == "ORGANIZATION"
    assert LABEL_MAPPING.get("LOC") == "LOCATION"


def test_ner_entity_extraction_fallback_or_ml():
    text = (
        "Rahul Sharma from Acme Cloud Solutions Pvt Ltd visited Mumbai "
        "to discuss enterprise security and document intelligence."
    )
    entities = ner_service.extract_entities(text)
    assert len(entities) > 0

    entity_types = {e["type"] for e in entities}
    assert ("PERSON" in entity_types) or ("ORGANIZATION" in entity_types) or ("LOCATION" in entity_types)

    # Check entity format
    for ent in entities:
        assert "text" in ent
        assert "type" in ent
        assert "confidence" in ent
        assert 0.0 <= ent["confidence"] <= 1.0


def test_ner_empty_text():
    assert ner_service.extract_entities("") == []
    assert ner_service.extract_entities("   ") == []

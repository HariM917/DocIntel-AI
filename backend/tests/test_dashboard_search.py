import pytest
from fastapi.testclient import TestClient


def test_dashboard_stats(client: TestClient):
    res = client.get("/api/dashboard/stats")
    assert res.status_code == 200
    data = res.json()
    assert "total_processed" in data
    assert "extraction_accuracy" in data
    assert "protected_entities" in data
    assert "time_saved" in data
    assert "type_distribution" in data
    assert "recent_documents" in data


def test_search_documents(client: TestClient):
    res = client.get("/api/search?q=Invoice")
    assert res.status_code == 200
    data = res.json()
    assert "query" in data
    assert data["query"] == "Invoice"
    assert "results" in data


def test_security_rules_flow(client: TestClient):
    # 1. Get rules
    rules_res = client.get("/api/security/rules")
    assert rules_res.status_code == 200
    rules = rules_res.json()
    assert len(rules) >= 6

    # 2. Update rule
    first_rule = rules[0]
    rule_id = first_rule["rule_id"]
    new_state = not first_rule["enabled"]

    put_res = client.put(
        f"/api/security/rules/{rule_id}",
        json={"enabled": new_state},
    )
    assert put_res.status_code == 200
    assert put_res.json()["enabled"] == new_state

    # Restore state
    client.put(
        f"/api/security/rules/{rule_id}",
        json={"enabled": first_rule["enabled"]},
    )


def test_chat_assistant(client: TestClient):
    # 1. General query
    res = client.post(
        "/api/chat",
        json={"message": "What is the invoice amount?"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "sources" in data
    assert "confidence" in data

    # 2. Empty query validation
    bad_res = client.post(
        "/api/chat",
        json={"message": "   "},
    )
    assert bad_res.status_code == 400

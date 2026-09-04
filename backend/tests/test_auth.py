import pytest
from fastapi.testclient import TestClient


def test_auth_flow(client: TestClient):
    import time
    unique_email = f"test_user_{int(time.time())}@docintel.ai"
    password = "SecurePassword123!"

    # 1. Register
    reg_res = client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": password,
            "full_name": "Test User",
        },
    )
    assert reg_res.status_code == 200
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == unique_email
    token = reg_data["access_token"]

    # 2. Duplicate registration fails
    dup_res = client.post(
        "/api/auth/register",
        json={
            "email": unique_email,
            "password": password,
            "full_name": "Duplicate User",
        },
    )
    assert dup_res.status_code == 400

    # 3. Login with correct credentials
    login_res = client.post(
        "/api/auth/login",
        json={"email": unique_email, "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data

    # 4. Login with incorrect password fails
    bad_login = client.post(
        "/api/auth/login",
        json={"email": unique_email, "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401

    # 5. Access /api/auth/me with valid token
    me_res = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["email"] == unique_email

    # 6. Access /api/auth/me without token fails
    no_token_res = client.get("/api/auth/me")
    assert no_token_res.status_code == 401

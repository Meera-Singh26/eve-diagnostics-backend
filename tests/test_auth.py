def test_signup_and_me(client):
    res = client.post(
        "/auth/signup", json={"email": "Asha@Example.com", "full_name": " Asha ", "password": "Password123"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "asha@example.com"
    assert body["full_name"] == "Asha"
    assert body["is_admin"] is False
    assert "password" not in body and "hashed_password" not in body


def test_duplicate_email_rejected_case_insensitive(client):
    payload = {"email": "asha@example.com", "full_name": "Asha", "password": "Password123"}
    assert client.post("/auth/signup", json=payload).status_code == 201
    res = client.post("/auth/signup", json={**payload, "email": "ASHA@example.com"})
    assert res.status_code == 409


def test_signup_validation(client):
    base = {"email": "a@example.com", "full_name": "A", "password": "Password123"}
    assert client.post("/auth/signup", json={**base, "email": "not-an-email"}).status_code == 422
    assert client.post("/auth/signup", json={**base, "password": "short1"}).status_code == 422
    assert client.post("/auth/signup", json={**base, "password": "onlyletters"}).status_code == 422
    assert client.post("/auth/signup", json={**base, "full_name": "   "}).status_code == 422


def test_login_and_me(client, user_headers):
    res = client.get("/auth/me", headers=user_headers)
    assert res.status_code == 200
    assert res.json()["email"] == "asha@example.com"


def test_login_wrong_password_and_unknown_user(client, user_headers):
    bad = client.post("/auth/login", data={"username": "asha@example.com", "password": "Wrong12345"})
    unknown = client.post("/auth/login", data={"username": "nobody@example.com", "password": "Password123"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


def test_protected_route_needs_valid_token(client):
    assert client.get("/auth/me").status_code == 401
    res = client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert res.status_code == 401
    assert res.headers["www-authenticate"] == "Bearer"

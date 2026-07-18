def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_login_success_and_me(client, auth_headers):
    me = client.get("/api/v1/auth/me", headers=auth_headers)
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "admin"
    assert body["role"] == "admin"


def test_login_wrong_password(client):
    resp = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "nope"}
    )
    assert resp.status_code == 401


def test_oauth2_token_form(client):
    resp = client.post(
        "/api/v1/auth/token", data={"username": "admin", "password": "admin123"}
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_protected_route_requires_auth(client):
    resp = client.get("/api/v1/students")
    assert resp.status_code == 401


def test_invalid_token_rejected(client):
    resp = client.get("/api/v1/students", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401


def test_register_creates_school_account(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "school_name": "Riverdale Elementary",
            "username": "riverdale",
            "password": "s3cret-pass",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "riverdale"
    assert body["role"] == "school"
    assert body["school_name"] == "Riverdale Elementary"


def test_register_then_login(client):
    client.post(
        "/api/v1/auth/register",
        json={"school_name": "Hilltop High", "username": "hilltop", "password": "s3cret-pass"},
    )
    resp = client.post(
        "/api/v1/auth/login", json={"username": "hilltop", "password": "s3cret-pass"}
    )
    assert resp.status_code == 200
    assert resp.json()["token_type"] == "bearer"


def test_register_duplicate_username_rejected(client):
    payload = {"school_name": "Hilltop High", "username": "hilltop", "password": "s3cret-pass"}
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201
    resp = client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409


def test_register_validation(client):
    # Password too short.
    resp = client.post(
        "/api/v1/auth/register",
        json={"school_name": "Hilltop High", "username": "hilltop", "password": "short"},
    )
    assert resp.status_code == 422

    # Username with invalid characters.
    resp = client.post(
        "/api/v1/auth/register",
        json={"school_name": "Hilltop High", "username": "bad user!", "password": "s3cret-pass"},
    )
    assert resp.status_code == 422

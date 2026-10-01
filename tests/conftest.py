import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.core.security import hash_password, sign_webhook  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def _login(client, email, password="Password123"):
    res = client.post("/auth/login", data={"username": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def make_user(client, email="asha@example.com", name="Asha Rao"):
    res = client.post("/auth/signup", json={"email": email, "full_name": name, "password": "Password123"})
    assert res.status_code == 201, res.text
    return _login(client, email)


@pytest.fixture
def user_headers(client):
    return make_user(client)


@pytest.fixture
def other_headers(client):
    return make_user(client, "ravi@example.com", "Ravi K")


@pytest.fixture
def admin_headers(client, db):
    db.add(
        models.User(
            email="admin@example.com",
            full_name="Admin",
            hashed_password=hash_password("Password123"),
            is_admin=True,
        )
    )
    db.commit()
    return _login(client, "admin@example.com")


@pytest.fixture
def catalog(db):
    """One centre offering one test at 500.00"""
    test = models.DiagnosticTest(name="Lipid Profile")
    centre = models.DiagnosticCentre(name="Eve Andheri", city="Mumbai", address="12 Link Road")
    db.add_all([test, centre])
    db.flush()
    db.add(models.CentreTest(centre_id=centre.id, test_id=test.id, price=Decimal("500.00")))
    db.commit()
    return {"centre_id": centre.id, "test_id": test.id, "price": "500.00"}


def future(days=3):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


@pytest.fixture
def booking(client, user_headers, catalog):
    res = client.post(
        "/bookings/",
        json={"centre_id": catalog["centre_id"], "test_id": catalog["test_id"], "appointment_at": future()},
        headers=user_headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


def send_webhook(client, payload, signature=None):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-Webhook-Signature": signature or sign_webhook(body)}
    return client.post("/payments/webhook/", content=body, headers=headers)

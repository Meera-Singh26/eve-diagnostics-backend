from datetime import datetime, timedelta, timezone

from tests.conftest import future


def _payload(catalog, **over):
    return {"centre_id": catalog["centre_id"], "test_id": catalog["test_id"], "appointment_at": future(), **over}


def test_create_booking_snapshots_price(client, user_headers, catalog):
    res = client.post("/bookings/", json=_payload(catalog), headers=user_headers)
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "PENDING"
    assert body["amount"] == "500.00"
    assert body["centre"]["name"] == "Eve Andheri"
    assert body["test"]["name"] == "Lipid Profile"
    assert body["payments"] == []


def test_booking_requires_auth(client, catalog):
    assert client.post("/bookings/", json=_payload(catalog)).status_code == 401
    assert client.get("/bookings/").status_code == 401


def test_booking_validation(client, user_headers, catalog):
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    naive = (datetime.now() + timedelta(days=2)).replace(tzinfo=None).isoformat()
    assert client.post("/bookings/", json=_payload(catalog, appointment_at=past), headers=user_headers).status_code == 422
    assert client.post("/bookings/", json=_payload(catalog, appointment_at=naive), headers=user_headers).status_code == 422
    assert client.post("/bookings/", json=_payload(catalog, appointment_at="tomorrow"), headers=user_headers).status_code == 422
    assert client.post("/bookings/", json={"centre_id": 1}, headers=user_headers).status_code == 422


def test_centre_must_offer_the_test(client, user_headers, catalog):
    res = client.post("/bookings/", json=_payload(catalog, test_id=9999), headers=user_headers)
    assert res.status_code == 404
    res = client.post("/bookings/", json=_payload(catalog, centre_id=9999), headers=user_headers)
    assert res.status_code == 404


def test_same_slot_twice_is_rejected_until_cancelled(client, user_headers, catalog):
    payload = _payload(catalog)
    first = client.post("/bookings/", json=payload, headers=user_headers)
    assert first.status_code == 201
    assert client.post("/bookings/", json=payload, headers=user_headers).status_code == 409

    client.post(f"/bookings/{first.json()['id']}/cancel", headers=user_headers)
    assert client.post("/bookings/", json=payload, headers=user_headers).status_code == 201


def test_users_only_see_their_own_bookings(client, user_headers, other_headers, booking):
    assert client.get(f"/bookings/{booking['id']}", headers=user_headers).status_code == 200
    assert client.get(f"/bookings/{booking['id']}", headers=other_headers).status_code == 404
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=other_headers).status_code == 404

    assert client.get("/bookings/", headers=user_headers).json()["total"] == 1
    assert client.get("/bookings/", headers=other_headers).json()["total"] == 0


def test_invalid_booking_id(client, user_headers):
    assert client.get("/bookings/99999", headers=user_headers).status_code == 404
    assert client.get("/bookings/abc", headers=user_headers).status_code == 422


def test_cancel_is_idempotent(client, user_headers, booking):
    url = f"/bookings/{booking['id']}/cancel"
    assert client.post(url, headers=user_headers).json()["status"] == "CANCELLED"
    assert client.post(url, headers=user_headers).json()["status"] == "CANCELLED"


def test_list_status_filter(client, user_headers, booking):
    assert client.get("/bookings/?status=PENDING", headers=user_headers).json()["total"] == 1
    assert client.get("/bookings/?status=CONFIRMED", headers=user_headers).json()["total"] == 0
    assert client.get("/bookings/?status=WHATEVER", headers=user_headers).status_code == 422

def _pay(client, headers, booking_id, outcome=None):
    body = {"booking_id": booking_id}
    if outcome:
        body["simulate_outcome"] = outcome
    return client.post("/payments/", json=body, headers=headers)


def _status(client, headers, booking_id):
    return client.get(f"/bookings/{booking_id}", headers=headers).json()["status"]


def test_successful_payment_confirms_booking(client, user_headers, booking):
    res = _pay(client, user_headers, booking["id"], "SUCCESS")
    assert res.status_code == 201
    assert res.json()["status"] == "SUCCESS"
    assert res.json()["amount"] == "500.00"
    assert res.json()["reference"].startswith("pay_")
    assert _status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_failed_payment_marks_booking_failed_and_can_be_retried(client, user_headers, booking):
    assert _pay(client, user_headers, booking["id"], "FAILED").json()["status"] == "FAILED"
    assert _status(client, user_headers, booking["id"]) == "FAILED"

    assert _pay(client, user_headers, booking["id"], "FAILED").status_code == 201
    assert _pay(client, user_headers, booking["id"], "SUCCESS").status_code == 201
    detail = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert detail["status"] == "CONFIRMED"
    assert [p["status"] for p in detail["payments"]] == ["FAILED", "FAILED", "SUCCESS"]


def test_cannot_pay_twice(client, user_headers, booking):
    _pay(client, user_headers, booking["id"], "SUCCESS")
    res = _pay(client, user_headers, booking["id"], "SUCCESS")
    assert res.status_code == 409
    detail = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert len(detail["payments"]) == 1


def test_cannot_pay_cancelled_booking(client, user_headers, booking):
    client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert _pay(client, user_headers, booking["id"], "SUCCESS").status_code == 409


def test_payment_authorization_and_bad_input(client, user_headers, other_headers, booking):
    assert client.post("/payments/", json={"booking_id": booking["id"]}).status_code == 401
    assert _pay(client, other_headers, booking["id"], "SUCCESS").status_code == 404
    assert _pay(client, user_headers, 99999, "SUCCESS").status_code == 404
    assert client.post("/payments/", json={}, headers=user_headers).status_code == 422
    assert client.post("/payments/", json={"booking_id": "x"}, headers=user_headers).status_code == 422
    assert client.post("/payments/", json={"booking_id": 0}, headers=user_headers).status_code == 422
    assert _pay(client, user_headers, booking["id"], "MAYBE").status_code == 422
    assert _status(client, user_headers, booking["id"]) == "PENDING"


def test_random_outcome_is_one_of_the_two(client, user_headers, booking):
    res = _pay(client, user_headers, booking["id"])
    assert res.json()["status"] in {"SUCCESS", "FAILED"}


def test_pending_payment_blocks_a_second_attempt(client, user_headers, booking):
    assert _pay(client, user_headers, booking["id"], "PENDING").json()["status"] == "PENDING"
    assert _status(client, user_headers, booking["id"]) == "PENDING"
    assert _pay(client, user_headers, booking["id"], "SUCCESS").status_code == 409


def test_get_payment_is_owner_only(client, user_headers, other_headers, booking):
    pid = _pay(client, user_headers, booking["id"], "SUCCESS").json()["id"]
    assert client.get(f"/payments/{pid}", headers=user_headers).status_code == 200
    assert client.get(f"/payments/{pid}", headers=other_headers).status_code == 404

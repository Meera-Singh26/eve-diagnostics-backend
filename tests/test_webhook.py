from sqlalchemy import func, select

from app import models
from tests.conftest import send_webhook


def _pay(client, headers, booking_id, outcome):
    return client.post(
        "/payments/", json={"booking_id": booking_id, "simulate_outcome": outcome}, headers=headers
    ).json()


def _booking_status(client, headers, booking_id):
    return client.get(f"/bookings/{booking_id}", headers=headers).json()["status"]


def _event(payment, event_id="evt_1", status="SUCCESS", **extra):
    return {"event_id": event_id, "payment_reference": payment["reference"], "status": status, **extra}


def test_rejects_missing_or_bad_signature(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    assert client.post("/payments/webhook/", json=_event(payment)).status_code == 401
    assert send_webhook(client, _event(payment), signature="0" * 64).status_code == 401
    assert _booking_status(client, user_headers, booking["id"]) == "PENDING"


def test_webhook_confirms_pending_payment(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    res = send_webhook(client, _event(payment, amount="500.00"))
    assert res.status_code == 200
    assert res.json() == {"status": "processed", "event_id": "evt_1", "outcome": "payment_success"}
    assert _booking_status(client, user_headers, booking["id"]) == "CONFIRMED"
    assert client.get(f"/payments/{payment['id']}", headers=user_headers).json()["status"] == "SUCCESS"


def test_same_event_many_times_changes_nothing(client, user_headers, booking, db):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    event = _event(payment)

    first = send_webhook(client, event)
    second = send_webhook(client, event)
    third = send_webhook(client, event)

    assert first.json()["status"] == "processed"
    assert second.json()["status"] == third.json()["status"] == "duplicate"
    assert second.status_code == third.status_code == 200

    assert db.scalar(select(func.count()).select_from(models.Payment)) == 1
    assert db.scalar(select(func.count()).select_from(models.Booking)) == 1
    assert db.scalar(select(func.count()).select_from(models.WebhookEvent)) == 1
    assert _booking_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_new_event_for_settled_payment_is_a_no_op(client, user_headers, booking, db):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    send_webhook(client, _event(payment, "evt_1"))
    res = send_webhook(client, _event(payment, "evt_2"))
    assert res.json()["outcome"] == "no_change"
    assert db.scalar(select(func.count()).select_from(models.Payment)) == 1
    assert _booking_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_late_failure_cannot_undo_a_success(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "SUCCESS")
    res = send_webhook(client, _event(payment, "evt_late", status="FAILED"))
    assert res.json()["outcome"] == "ignored_downgrade"
    assert _booking_status(client, user_headers, booking["id"]) == "CONFIRMED"
    assert client.get(f"/payments/{payment['id']}", headers=user_headers).json()["status"] == "SUCCESS"


def test_webhook_failure_marks_booking_failed(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    res = send_webhook(client, _event(payment, status="FAILED"))
    assert res.json()["outcome"] == "payment_failed"
    assert _booking_status(client, user_headers, booking["id"]) == "FAILED"


def test_provider_can_confirm_a_payment_we_marked_failed(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "FAILED")
    send_webhook(client, _event(payment))
    assert _booking_status(client, user_headers, booking["id"]) == "CONFIRMED"


def test_success_after_cancellation_does_not_revive_booking(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    res = send_webhook(client, _event(payment))
    assert res.json()["outcome"] == "success_on_cancelled_booking"
    assert _booking_status(client, user_headers, booking["id"]) == "CANCELLED"


def test_unknown_reference_is_404_and_can_be_retried(client, user_headers, booking):
    res = send_webhook(client, {"event_id": "evt_x", "payment_reference": "pay_nope", "status": "SUCCESS"})
    assert res.status_code == 404

    payment = _pay(client, user_headers, booking["id"], "PENDING")
    # the failed attempt above must not have burned the event id
    ok = send_webhook(client, {"event_id": "evt_x", "payment_reference": payment["reference"], "status": "SUCCESS"})
    assert ok.json()["status"] == "processed"


def test_amount_mismatch_rejected(client, user_headers, booking):
    payment = _pay(client, user_headers, booking["id"], "PENDING")
    res = send_webhook(client, _event(payment, amount="1.00"))
    assert res.status_code == 400
    assert _booking_status(client, user_headers, booking["id"]) == "PENDING"


def test_invalid_payloads(client):
    assert send_webhook(client, {"event_id": "e"}).status_code == 422
    assert send_webhook(client, {"event_id": "e", "payment_reference": "p", "status": "PENDING"}).status_code == 422
    assert send_webhook(client, {"event_id": "", "payment_reference": "p", "status": "SUCCESS"}).status_code == 422

    from app.core.security import sign_webhook

    raw = b"not json"
    res = client.post("/payments/webhook/", content=raw, headers={"X-Webhook-Signature": sign_webhook(raw)})
    assert res.status_code == 422

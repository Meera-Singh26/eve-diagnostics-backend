# EVE Diagnostics Booking API

Backend for booking diagnostic tests at centres, with a simulated payment service and an idempotent payment webhook.

Stack: Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL, JWT (PyJWT), bcrypt, pytest.

## Running it

### With Docker (easiest)

```bash
docker compose up --build
```

API on http://localhost:8000, Swagger UI on http://localhost:8000/docs.
The container seeds an admin user and a few centres/tests on start.

### Locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # then point DATABASE_URL at your Postgres
python -m app.seed              # creates tables, admin user, sample data
uvicorn app.main:app --reload
```

Seeded admin: `admin@eve.test` / `Admin12345` (change via `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`).

### Tests

```bash
pytest
```

Tests run on in-memory SQLite so they need nothing installed besides the requirements. The app itself targets Postgres.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/signup` | none | |
| POST | `/auth/login` | none | form fields `username` (the email) and `password` |
| GET | `/auth/me` | user | |
| GET | `/tests/` | none | `q`, `limit`, `offset` |
| POST | `/tests/` | admin | |
| GET | `/centres/` | none | `city`, `test_id`, `limit`, `offset` |
| GET | `/centres/{id}` | none | includes tests and prices |
| POST | `/centres/` | admin | |
| POST | `/centres/{id}/tests` | admin | attach a test with a price |
| POST | `/bookings/` | user | |
| GET | `/bookings/` | user | own bookings, `status`, `limit`, `offset` |
| GET | `/bookings/{id}` | user | includes its payments |
| POST | `/bookings/{id}/cancel` | user | |
| POST | `/payments/` | user | fake gateway |
| GET | `/payments/{id}` | user | |
| POST | `/payments/webhook/` | signature | provider callback |
| GET | `/health` | none | |

Errors look like `{"error": {"code": "conflict", "message": "..."}}`. Request body validation errors use FastAPI's standard 422 format.

### Example flow

```bash
BASE=http://localhost:8000

curl -X POST $BASE/auth/signup -H 'Content-Type: application/json' \
  -d '{"email":"asha@example.com","full_name":"Asha Rao","password":"Password123"}'

TOKEN=$(curl -s -X POST $BASE/auth/login \
  -d 'username=asha@example.com&password=Password123' | python -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

curl "$BASE/centres/?city=Mumbai"

curl -X POST $BASE/bookings/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"centre_id":1,"test_id":1,"appointment_at":"2026-12-01T09:30:00+05:30"}'

curl -X POST $BASE/payments/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"booking_id":1}'
```

`POST /payments/` picks SUCCESS or FAILED randomly (80% success, `PAYMENT_SUCCESS_RATE`). To get a fixed result pass `"simulate_outcome": "SUCCESS"` or `"FAILED"`. Passing `"PENDING"` leaves the payment open, and the fake provider is then expected to call the webhook.

### Webhook

Requests must carry `X-Webhook-Signature`, the hex HMAC-SHA256 of the raw body using `WEBHOOK_SECRET`.

```bash
BODY='{"event_id":"evt_1001","payment_reference":"pay_xxx","status":"SUCCESS","amount":"350.00"}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SECRET" | awk '{print $NF}')

curl -X POST $BASE/payments/webhook/ -H 'Content-Type: application/json' \
  -H "X-Webhook-Signature: $SIG" -d "$BODY"
```

Response: `{"status":"processed","event_id":"evt_1001","outcome":"payment_success"}`.
Sending the same event again returns 200 with `"status":"duplicate"` and changes nothing.

## Database design

```
users            id, email (unique), full_name, hashed_password, is_admin, created_at
diagnostic_centres   id, name, city, address        unique(name, city)
diagnostic_tests     id, name (unique), description
centre_tests         id, centre_id, test_id, price  unique(centre_id, test_id), check price > 0
bookings         id, user_id, centre_id, test_id, appointment_at, amount, status, created_at, updated_at
payments         id, booking_id, reference (unique), amount, status, created_at, updated_at
webhook_events   id, event_id (unique), payment_reference, payload (json), outcome, received_at
```

Some decisions worth mentioning:

- **Price lives on `centre_tests`**, because the same test costs different amounts at different centres. A booking copies the price into `bookings.amount`, so changing a price later does not rewrite history.
- **One payment row per attempt.** A booking can have several failed payments and one successful one. A partial unique index (`booking_id` where `status = 'SUCCESS'`) enforces "charged at most once" in the database, not just in code.
- **`webhook_events.event_id` is unique.** That is the idempotency key, see below.
- Money is `NUMERIC(10,2)`, never float.
- Statuses are stored as short strings rather than native Postgres enums, so adding a state later does not need an `ALTER TYPE`.

### Booking states

```
PENDING   -> CONFIRMED | FAILED | CANCELLED
FAILED    -> CONFIRMED | CANCELLED      (payment can be retried)
CONFIRMED -> CANCELLED
CANCELLED -> (nothing)
```

Transitions go through one function (`move_to` in `services/bookings.py`), so an illegal move is a 409 everywhere.

## How the webhook stays idempotent

1. The signature is checked on the raw body first.
2. The handler inserts a row into `webhook_events` with the provider's `event_id`, in the same transaction as the state change.
3. If the insert violates the unique key, the event was already handled (or is being handled by a concurrent request), so we roll back and answer 200 `duplicate`. Two identical requests arriving at the same moment are safe because the second insert waits on the first one's transaction.
4. The booking row is locked (`SELECT ... FOR UPDATE`) before the payment status is touched, so the webhook and `POST /payments/` cannot interleave badly.
5. The webhook only ever updates the existing payment found by `payment_reference`. It never creates payments or bookings.

Extra rules on top of that: a `SUCCESS` payment is never downgraded by a later `FAILED` event, a success for an already cancelled booking is recorded but does not revive the booking, and an amount that does not match the payment is rejected. If the reference is unknown the response is 404 and the event id is not stored, so the provider's retry works once the payment exists.

## Assumptions

- Login takes form data (`username` = email) because that is what Swagger's Authorize button expects.
- Only admins can create centres, tests and prices. Admins are created by the seed script, never by signup.
- `appointment_at` must be timezone aware and in the future.
- A user cannot hold two active bookings for the same test, centre and time.
- Trying to read or change someone else's booking returns 404 rather than 403, so booking ids cannot be probed.
- Cancelling a confirmed booking does not trigger a refund, since there is no real gateway.
- A failed payment leaves the booking in `FAILED`, and the user can pay again.
- Tables are created on startup with `create_all`.

## What I would do with more time

- Alembic migrations instead of `create_all`.
- Expire `PENDING` payments that never got a webhook (background job), and a real refund flow for cancellations.
- Async retry queue (Celery or similar) for webhook side effects like notifications, and a dead-letter table for events that keep failing.
- Rate limiting on login and signup, refresh tokens, and account lockout.
- Slot capacity per centre, so two people cannot take the same slot when a centre only has one machine.
- Redis cache for the centre and test listings, which are read heavy and rarely change.
- Run the tests against Postgres in CI, especially the concurrency paths that SQLite cannot exercise.

## Layout

```
app/
  api/        route handlers and dependencies (thin)
  services/   business rules and DB work
  schemas/    request and response models
  core/       config, security, logging, errors
  db/         engine and session
  models.py   SQLAlchemy tables
  seed.py     sample data
tests/
```

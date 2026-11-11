"""Integration tests against the live API: auth, ownership, CRUD, cycles and exchange state machine.

Every test user is unique and trades in CHF, so these tests never touch the seeded USD demo cycles.
"""

import uuid

import httpx

from tests.conftest import API_URL

PASSWORD = "testpass123"


def _new_client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=30.0)


def _register(client: httpx.Client, name: str, marker: str) -> dict:
    email = f"{name.lower()}-{uuid.uuid4().hex[:6]}{marker}"
    response = client.post("/v1/auth/register", json={"name": name, "email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def _listing(client, **overrides):
    payload = {
        "title": "Test item",
        "description": "test",
        "type": "goods",
        "category": "Electronics",
        "estimated_value": 100,
        "currency": "CHF",
    }
    payload.update(overrides)
    response = client.post("/v1/listings", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _want(client, listing_id, **overrides):
    payload = {
        "title": "Test want",
        "category": "Electronics",
        "target_type": "goods",
        "min_value": 50,
        "max_value": 200,
        "currency": "CHF",
        "listing_id": listing_id,
    }
    payload.update(overrides)
    response = client.post("/v1/wants", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_register_login_me_logout(cleanup_marker):
    with _new_client() as client:
        user = _register(client, "Alice", cleanup_marker)
        assert "password_hash" not in user
        me = client.get("/v1/auth/me")
        assert me.status_code == 200 and me.json()["id"] == user["id"]
        assert client.post("/v1/auth/logout").status_code == 200
        client.cookies.clear()
        assert client.get("/v1/auth/me").status_code == 401
        login = client.post("/v1/auth/login", json={"email": user["email"], "password": PASSWORD})
        assert login.status_code == 200
        bad = client.post("/v1/auth/login", json={"email": user["email"], "password": "wrong-password"})
        assert bad.status_code == 401


def test_duplicate_email_and_validation(cleanup_marker):
    with _new_client() as client:
        user = _register(client, "Bob", cleanup_marker)
        dup = client.post("/v1/auth/register", json={"name": "Bob", "email": user["email"], "password": PASSWORD})
        assert dup.status_code == 409
        short = client.post("/v1/auth/register", json={"name": "B", "email": "x@y.dev", "password": "123"})
        assert short.status_code == 422


def test_profile_update(cleanup_marker):
    with _new_client() as client:
        _register(client, "Carol", cleanup_marker)
        updated = client.patch("/v1/users/me", json={"bio": "maker", "skills": ["pottery"]})
        assert updated.status_code == 200
        assert updated.json()["skills"] == ["pottery"]


def test_listing_crud_ownership_and_filters(cleanup_marker):
    with _new_client() as owner, _new_client() as other:
        _register(owner, "Dana", cleanup_marker)
        _register(other, "Eve", cleanup_marker)
        listing = _listing(owner, title="Unique zebra lamp", estimated_value=77)

        assert other.patch(f"/v1/listings/{listing['id']}", json={"title": "hijack"}).status_code == 403
        assert other.delete(f"/v1/listings/{listing['id']}").status_code == 403
        assert other.post("/v1/listings", json={"title": "x"}).status_code == 422

        found = owner.get("/v1/listings", params={"q": "zebra lamp", "min_value": 50, "max_value": 100})
        assert found.status_code == 200
        assert any(item["id"] == listing["id"] for item in found.json()["items"])
        page = owner.get("/v1/listings", params={"page": 1, "page_size": 2})
        assert page.json()["page_size"] == 2 and len(page.json()["items"]) <= 2

        patched = owner.patch(f"/v1/listings/{listing['id']}", json={"estimated_value": 88})
        assert patched.status_code == 200 and patched.json()["estimated_value"] == 88
        assert owner.delete(f"/v1/listings/{listing['id']}").status_code == 200
        assert owner.get(f"/v1/listings/{listing['id']}").status_code == 404


def test_want_ownership_rules(cleanup_marker):
    with _new_client() as owner, _new_client() as other:
        _register(owner, "Finn", cleanup_marker)
        _register(other, "Gia", cleanup_marker)
        mine = _listing(owner)
        theirs = _listing(other)
        bad = owner.post(
            "/v1/wants",
            json={"title": "x want", "min_value": 1, "max_value": 2, "listing_id": theirs["id"], "currency": "CHF"},
        )
        assert bad.status_code == 403
        inverted = owner.post("/v1/wants", json={"title": "x want", "min_value": 10, "max_value": 2})
        assert inverted.status_code == 422
        want = _want(owner, mine["id"])
        assert other.delete(f"/v1/wants/{want['id']}").status_code == 403
        assert owner.delete(f"/v1/wants/{want['id']}").status_code == 200


def test_two_party_cycle_full_lifecycle(cleanup_marker):
    tag = uuid.uuid4().hex[:6]
    with _new_client() as a, _new_client() as b, _new_client() as outsider:
        user_a = _register(a, "Hana", cleanup_marker)
        user_b = _register(b, "Ivan", cleanup_marker)
        _register(outsider, "Jo", cleanup_marker)
        # Unique category + CHF keeps this cycle isolated from every other test and from the seed.
        la = _listing(a, title=f"widget-{tag}", category="Tools & Workshop", estimated_value=120)
        lb = _listing(b, title=f"gadget-{tag}", category="Sports & Outdoors", estimated_value=100)
        _want(a, la["id"], category="Sports & Outdoors", min_value=80, max_value=150)
        _want(b, lb["id"], category="Tools & Workshop", min_value=80, max_value=150)

        cycles = a.get("/v1/cycles", params={"max_nodes": 2, "limit": 50}).json()["cycles"]
        cycle = next(c for c in cycles if set(c["participant_ids"]) == {user_a["id"], user_b["id"]})
        balances = {p["user_id"]: p["balance_amount"] for p in cycle["participants"]}
        assert balances == {user_a["id"]: -20.0, user_b["id"]: 20.0}

        assert outsider.post(
            "/v1/exchanges/from-cycle", json={"cycle_key": cycle["key"], "participant_ids": cycle["participant_ids"]}
        ).status_code == 403

        proposed = a.post(
            "/v1/exchanges/from-cycle", json={"cycle_key": cycle["key"], "participant_ids": cycle["participant_ids"]}
        )
        assert proposed.status_code == 201, proposed.text
        exchange_id = proposed.json()["exchange"]["id"]

        # Listing is now reserved: cannot be proposed again, re-priced, or deleted.
        again = a.post(
            "/v1/exchanges/from-cycle", json={"cycle_key": cycle["key"], "participant_ids": cycle["participant_ids"]}
        )
        assert again.status_code == 409
        assert a.patch(f"/v1/listings/{la['id']}", json={"estimated_value": 999}).status_code == 409
        assert a.delete(f"/v1/listings/{la['id']}").status_code == 409
        assert outsider.get(f"/v1/exchanges/{exchange_id}").status_code == 403

        # Approval then change request invalidates earlier approvals.
        assert a.post(f"/v1/exchanges/{exchange_id}/approve", json={"decision": "approved"}).json()["exchange"]["approvals_current"] == 1
        changed = b.post(f"/v1/exchanges/{exchange_id}/request-changes", json={"note": "include the case"}).json()["exchange"]
        assert changed["revision"] == 2 and changed["approvals_current"] == 0

        # Payments and fulfilment are blocked until everyone approves the current revision.
        assert b.post(f"/v1/exchanges/{exchange_id}/fulfilment").status_code == 409

        a.post(f"/v1/exchanges/{exchange_id}/approve", json={"decision": "approved"})
        approved = b.post(f"/v1/exchanges/{exchange_id}/approve", json={"decision": "approved"}).json()["exchange"]
        # B owes 20 CHF, so the exchange waits on a verified payment — never assumed paid.
        assert approved["status"] == "approved"  # payer has not started PayPal yet
        assert approved["payment_summary"]["required"] == 1
        assert approved["payment_summary"]["all_verified"] is False
        assert b.post(f"/v1/exchanges/{exchange_id}/fulfilment").status_code == 409

        # A owes nothing, so they cannot initiate a payment.
        assert a.post(f"/v1/exchanges/{exchange_id}/payments", json={}).status_code in (409, 503)

        cancelled = a.post(f"/v1/exchanges/{exchange_id}/cancel").json()["exchange"]
        assert cancelled["status"] == "cancelled"
        assert a.get(f"/v1/listings/{la['id']}").json()["status"] == "active"


def test_balanced_cycle_completes_without_payment(cleanup_marker):
    tag = uuid.uuid4().hex[:6]
    with _new_client() as a, _new_client() as b:
        user_a = _register(a, "Kai", cleanup_marker)
        user_b = _register(b, "Lea", cleanup_marker)
        la = _listing(a, title=f"book-{tag}", category="Books & Music", estimated_value=60)
        lb = _listing(b, title=f"jacket-{tag}", category="Fashion", estimated_value=60)
        _want(a, la["id"], category="Fashion", min_value=50, max_value=70)
        _want(b, lb["id"], category="Books & Music", min_value=50, max_value=70)
        cycle = next(
            c
            for c in a.get("/v1/cycles", params={"max_nodes": 2, "limit": 50}).json()["cycles"]
            if set(c["participant_ids"]) == {user_a["id"], user_b["id"]}
        )
        exchange_id = a.post(
            "/v1/exchanges/from-cycle", json={"cycle_key": cycle["key"], "participant_ids": cycle["participant_ids"]}
        ).json()["exchange"]["id"]
        a.post(f"/v1/exchanges/{exchange_id}/approve", json={"decision": "approved"})
        b.post(f"/v1/exchanges/{exchange_id}/approve", json={"decision": "approved"})
        assert a.post(f"/v1/exchanges/{exchange_id}/fulfilment").json()["exchange_status"] == "fulfillment_in_progress"
        assert b.post(f"/v1/exchanges/{exchange_id}/fulfilment").json()["exchange_status"] == "fulfillment_in_progress"
        assert a.post(f"/v1/exchanges/{exchange_id}/complete").json()["exchange"]["status"] == "completed"
        assert a.get(f"/v1/listings/{la['id']}").json()["status"] == "traded"
        unread = b.get("/v1/notifications/unread").json()
        assert unread["unread"] >= 1


def test_unauthenticated_and_unverified_webhook_rejected(cleanup_marker):
    with _new_client() as client:
        assert client.get("/v1/matches").status_code == 401
        assert client.get("/v1/wants").status_code == 401
        webhook = client.post("/v1/webhooks/paypal", json={"event_type": "PAYMENT.CAPTURE.COMPLETED", "resource": {}})
        # Never trusted without PayPal's signature verification.
        assert webhook.status_code in (400, 503)

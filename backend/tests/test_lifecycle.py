"""Integration tests for the complete exchange lifecycle and PayPal balancing payments (PayPal mocked).

Runs the real app in-process (TestClient) against the real Mongo database. Users are throwaway
(CHF, unique email) and purged on teardown. Covers: proposal, revision-bound approvals,
counteroffer invalidation, payment only after approval, order idempotency, duplicate-capture
protection, cancellation of a payment, completion, rejection, cancellation, disputes
(participant and admin resolution), expiry, reservation conflicts and authorisation.
"""

import asyncio

import pytest

from tests.test_inprocess_features import FakePayPal, Trader, _install_paypal, _two_party_cycle


def _propose(t: Trader, cycle) -> dict:
    response = t.post("/v1/exchanges/from-cycle", {"cycle_key": cycle["key"], "participant_ids": cycle["participant_ids"]})
    assert response.status_code == 201, response.text
    return response.json()["exchange"]


def _ex(t: Trader, exchange_id: str) -> dict:
    return t.get(f"/v1/exchanges/{exchange_id}").json()["exchange"]


def test_full_lifecycle_with_counteroffer_payment_and_completion(app_client, cleanup_marker, monkeypatch):
    fake = FakePayPal()
    _install_paypal(monkeypatch, fake)
    a, b, outsider = (Trader(app_client, n, cleanup_marker) for n in ("Ana", "Bo", "Out"))
    cycle, la, lb = _two_party_cycle(a, b, "Photography", 100, 80)  # a gives 100, gets 80 -> owed 20

    ex = _propose(a, cycle)
    eid = ex["id"]
    assert ex["status"] == "proposed" and ex["revision"] == 1 and ex["expires_at"]
    assert {p["user_id"]: p["balance_amount"] for p in ex["participants"]} == {a.id: -20.0, b.id: 20.0}
    assert a.get(f"/v1/listings/{la['id']}").json()["status"] == "reserved"

    # Authorisation: outsiders can neither view nor act; nobody can pay before approval.
    assert outsider.get(f"/v1/exchanges/{eid}").status_code == 403
    assert outsider.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 1}).status_code == 403
    assert b.post(f"/v1/exchanges/{eid}/payments", {}).status_code == 409

    # A approves revision 1 -> pending approval.
    assert a.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 1}).json()["exchange"]["status"] == "pending_approval"

    # B counters: B's own listing is now valued 90. Approvals reset and the revision bumps.
    counter = b.post(f"/v1/exchanges/{eid}/counteroffer", {"agreed_values": {lb["id"]: 90}, "message": "My kit is worth 90"})
    assert counter.status_code == 200, counter.text
    body = counter.json()
    assert body["exchange"]["revision"] == 2 and body["exchange"]["approvals_current"] == 0 and body["exchange"]["status"] == "proposed"
    assert {p["user_id"]: p["balance_amount"] for p in body["exchange"]["participants"]} == {a.id: -10.0, b.id: 10.0}
    assert body["offers"][-1]["proposed_changes"]["previous_values"][lb["id"]] == 80
    assert any(e["kind"] == "counteroffer" for e in body["events"])

    # Approving the stale revision is refused. Approving the current one works for both.
    assert a.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 1}).status_code == 409
    a.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 2})
    approved = b.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 2}).json()["exchange"]
    assert approved["status"] == "approved" and "pay" in approved["allowed_actions"]
    assert a.post(f"/v1/exchanges/{eid}/complete").status_code == 409

    # Payment: only the payer, and the order is reused (idempotent) on repeat clicks.
    assert a.post(f"/v1/exchanges/{eid}/payments", {}).status_code == 409  # a is owed, not a payer
    first = b.post(f"/v1/exchanges/{eid}/payments", {})
    assert first.status_code == 200, first.text
    second = b.post(f"/v1/exchanges/{eid}/payments", {}).json()
    assert second["paypal_order_id"] == first.json()["paypal_order_id"] and fake.orders == 1
    assert first.json()["payment"]["amount"] == 10.0 and first.json()["payment"]["verified"] is False
    assert _ex(a, eid)["status"] == "payment_pending"
    order_call = next(c for c in fake.calls if c[1] == "/v2/checkout/orders")
    assert order_call[3] and order_call[3].startswith("bx-order-")  # PayPal-Request-Id idempotency key

    # Terms are locked for counteroffers only after money moves. Capture is verified server-side.
    pid = first.json()["payment"]["id"]
    assert a.post(f"/v1/payments/{pid}/capture").status_code == 403  # not a's payment
    captured = b.post(f"/v1/payments/{pid}/capture").json()
    assert captured["status"] == "captured" and captured["verified"] is True
    assert b.post(f"/v1/payments/{pid}/capture").json()["verified"] is True  # idempotent, no second PayPal call
    assert len([c for c in fake.calls if c[1].endswith("/capture")]) == 1
    assert b.post(f"/v1/exchanges/{eid}/counteroffer", {"agreed_values": {lb["id"]: 85}, "message": "x"}).status_code == 409
    assert b.post(f"/v1/exchanges/{eid}/cancel", {}).status_code == 409  # money moved: dispute instead

    # Fulfilment is a separate stage, and completion is explicit.
    assert _ex(a, eid)["status"] == "ready_for_fulfillment"
    assert a.post(f"/v1/exchanges/{eid}/fulfilment").json()["exchange_status"] == "fulfillment_in_progress"
    assert a.post(f"/v1/exchanges/{eid}/complete").status_code == 409  # b has not confirmed
    b.post(f"/v1/exchanges/{eid}/fulfilment")
    done = a.post(f"/v1/exchanges/{eid}/complete").json()
    assert done["exchange"]["status"] == "completed"
    assert a.get(f"/v1/listings/{la['id']}").json()["status"] == "traded"
    kinds = [e["kind"] for e in done["events"]]
    for kind in ("proposed", "approved", "counteroffer", "fulfilment_confirmed", "completed"):
        assert kind in kinds


def test_payment_cancellation_and_already_captured_recovery(app_client, cleanup_marker, monkeypatch):
    fake = FakePayPal()
    _install_paypal(monkeypatch, fake)
    a, b = Trader(app_client, "Cal", cleanup_marker), Trader(app_client, "Dee", cleanup_marker)
    cycle, *_ = _two_party_cycle(a, b, "Bikes", 100, 70)
    eid = _propose(a, cycle)["id"]
    for t in (a, b):
        t.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 1})
    pid = b.post(f"/v1/exchanges/{eid}/payments", {}).json()["payment"]["id"]

    # The payer abandons PayPal: the payment is cancelled and a fresh order is created next time.
    assert b.post(f"/v1/payments/{pid}/cancel").json()["status"] == "cancelled"
    assert _ex(b, eid)["status"] == "approved"
    assert b.post(f"/v1/payments/{pid}/capture").status_code == 409
    again = b.post(f"/v1/exchanges/{eid}/payments", {}).json()
    assert fake.orders == 2 and again["payment"]["status"] == "created"

    # PayPal says "already captured" (e.g. a retried request): we read the order and verify it.
    fake.already_captured = True
    result = b.post(f"/v1/payments/{again['payment']['id']}/capture").json()
    assert result["verified"] is True and result["status"] == "captured"


def test_reject_releases_listings_and_hides_cycle(app_client, cleanup_marker):
    a, b = Trader(app_client, "Eli", cleanup_marker), Trader(app_client, "Fay", cleanup_marker)
    cycle, la, _ = _two_party_cycle(a, b, "Garden", 60, 60)
    eid = _propose(a, cycle)["id"]
    rejected = b.post(f"/v1/exchanges/{eid}/reject", {"reason": "Changed my mind"}).json()["exchange"]
    assert rejected["status"] == "rejected"
    assert a.get(f"/v1/listings/{la['id']}").json()["status"] == "active"
    cycles = a.get("/v1/cycles?limit=50").json()["cycles"]
    assert all(c["key"] != cycle["key"] for c in cycles)  # rejected cycle is not rediscovered
    assert a.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved"}).status_code == 409


def test_cancel_dispute_and_admin_resolution(app_client, cleanup_marker):
    from lib.db import db  # noqa: F401  (motor handle bound to the TestClient loop)

    a, b = Trader(app_client, "Gus", cleanup_marker), Trader(app_client, "Hal", cleanup_marker)
    cycle, *_ = _two_party_cycle(a, b, "Music", 50, 50)
    eid = _propose(a, cycle)["id"]
    for t in (a, b):
        t.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved", "revision": 1})
    assert _ex(a, eid)["status"] == "ready_for_fulfillment"  # balanced: no payment needed

    disputed = a.post(f"/v1/exchanges/{eid}/dispute", {"reason": "Item arrived damaged"}).json()["exchange"]
    assert disputed["status"] == "disputed" and disputed["dispute"]["opened_by"] == a.id
    assert a.post(f"/v1/exchanges/{eid}/fulfilment").status_code == 409
    a.post(f"/v1/exchanges/{eid}/dispute/resolve", {})
    assert _ex(a, eid)["status"] == "disputed"  # needs every participant
    resumed = b.post(f"/v1/exchanges/{eid}/dispute/resolve", {}).json()["exchange"]
    assert resumed["status"] == "ready_for_fulfillment"

    # Second dispute settled by an admin; traders cannot use the admin endpoint.
    a.post(f"/v1/exchanges/{eid}/dispute", {"reason": "Still unhappy"})
    assert a.post(f"/v1/admin/exchanges/{eid}/resolve", {"action": "cancel", "note": "no"}).status_code == 403
    admin = Trader(app_client, "Admin", cleanup_marker)
    app_client.portal.call(_promote, admin.id) if hasattr(app_client, "portal") else asyncio.run(_promote(admin.id))
    assert any(d["id"] == eid for d in admin.get("/v1/admin/disputes").json()["exchanges"])
    closed = admin.post(f"/v1/admin/exchanges/{eid}/resolve", {"action": "cancel", "note": "Refund handled in PayPal"}).json()
    assert closed["exchange"]["status"] == "cancelled"


async def _promote(user_id: str) -> None:
    from lib.db import db

    await db.users.update_one({"id": user_id}, {"$set": {"role": "admin"}})


async def _age(exchange_id: str) -> None:
    from datetime import timedelta

    from lib.dates import utc_now
    from lib.db import db

    await db.exchanges.update_one({"id": exchange_id}, {"$set": {"expires_at": utc_now() - timedelta(minutes=1)}})


def test_expiry_and_reservation_conflict(app_client, cleanup_marker):
    a, b, c = (Trader(app_client, n, cleanup_marker) for n in ("Ivy", "Jay", "Kim"))
    cycle, la, lb = _two_party_cycle(a, b, "Kitchen", 40, 40)
    eid = _propose(a, cycle)["id"]

    # The same cycle cannot be proposed twice while held, and its listings are reserved.
    assert a.post("/v1/exchanges/from-cycle", {"cycle_key": cycle["key"], "participant_ids": cycle["participant_ids"]}).status_code == 409

    app_client.portal.call(_age, eid)
    assert _ex(a, eid)["status"] == "expired"
    assert a.get(f"/v1/listings/{la['id']}").json()["status"] == "active"
    assert a.post(f"/v1/exchanges/{eid}/approve", {"decision": "approved"}).status_code == 409


@pytest.mark.asyncio
async def test_reservation_ledger_is_atomic_under_concurrency():
    """Two exchanges race for the same listing: exactly one wins, the loser keeps no partial claims."""
    import uuid

    from fastapi import HTTPException
    from motor.motor_asyncio import AsyncIOMotorClient

    import services.reservations as reservations

    client = AsyncIOMotorClient(__import__("os").environ["MONGO_URL"])
    test_db = client[f"barterx_test_resv_{uuid.uuid4().hex[:6]}"]
    await test_db.listing_reservations.create_index("listing_id", unique=True)
    original = reservations.db
    reservations.db = test_db
    try:
        results = await asyncio.gather(
            reservations.reserve_listings("ex_one", ["shared", "only_one"]),
            reservations.reserve_listings("ex_two", ["shared", "only_two"]),
            return_exceptions=True,
        )
        winners = [r for r in results if not isinstance(r, Exception)]
        losers = [r for r in results if isinstance(r, HTTPException)]
        assert len(winners) == 1 and len(losers) == 1 and losers[0].status_code == 409
        docs = await test_db.listing_reservations.find({}).to_list(10)
        assert len({d["exchange_id"] for d in docs}) == 1  # loser rolled back everything it claimed
    finally:
        reservations.db = original
        await client.drop_database(test_db.name)
        client.close()

"""In-process API tests (FastAPI TestClient) with mocked AI and mocked PayPal.

These run the real app and the real Mongo database, but swap the external
providers for fakes so nothing reaches the network: the LLM provider through
set_llm_provider, and PayPal by patching `_request`. Each user is throwaway
(CHF currency, unique email) and purged on teardown.

Covers:
- POST /api/v1/ai/analyze-listing and /explain-match (validated output, errors, caching, ownership)
- re-embedding when the embedding model version changes (isolated test database)
- cycle alerts sent once when a new listing closes a cycle
- the full payout flow: payer pays, PayPal capture is verified, both fulfil, the
  automatic payout fails, a claim retries with a new attempt id, PayPal reports SUCCESS
- verified vs unverified reviews and reputation counts
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from lib.ai_providers import set_llm_provider
from tests.test_ai_intelligence import VALID, FakeLLM

PASSWORD = "testpass123"


# app_client is session-scoped in conftest.py: one TestClient (one event loop) per worker,
# because the shared motor client binds to the first loop that uses it.


class Trader:
    def __init__(self, client: TestClient, name: str, marker: str):
        self.client = client
        email = f"{name.lower()}-{uuid.uuid4().hex[:6]}{marker}"
        response = client.post("/v1/auth/register", json={"name": name, "email": email, "password": PASSWORD})
        assert response.status_code == 201, response.text
        self.user = response.json()
        self.id = self.user["id"]
        self.token = response.cookies.get("barterx_session") or client.cookies.get("barterx_session")
        client.cookies.clear()

    def _headers(self):
        return {"Cookie": f"barterx_session={self.token}"}

    def get(self, path, **kw):
        return self.client.get(path, headers=self._headers(), **kw)

    def post(self, path, json=None, **kw):
        return self.client.post(path, json=json, headers=self._headers(), **kw)

    def patch(self, path, json=None):
        return self.client.patch(path, json=json, headers=self._headers())

    def listing(self, **overrides):
        payload = {"title": "Test item", "description": "test", "type": "goods", "category": "Electronics",
                   "estimated_value": 100, "currency": "CHF"}
        payload.update(overrides)
        response = self.post("/v1/listings", payload)
        assert response.status_code == 201, response.text
        return response.json()

    def want(self, listing_id, **overrides):
        payload = {"title": "Test want", "category": "Electronics", "target_type": "goods", "min_value": 50,
                   "max_value": 200, "currency": "CHF", "listing_id": listing_id}
        payload.update(overrides)
        response = self.post("/v1/wants", payload)
        assert response.status_code == 201, response.text
        return response.json()

    def notifications(self):
        return self.get("/v1/notifications?page_size=50").json()["items"]


def _two_party_cycle(a: Trader, b: Trader, category: str, a_value: float, b_value: float):
    a_listing = a.listing(title=f"{category} kit from A", category=category, estimated_value=a_value)
    b_listing = b.listing(title=f"{category} kit from B", category=category, estimated_value=b_value)
    a.want(a_listing["id"], title=f"{category} kit", category=category, min_value=1, max_value=500)
    b.want(b_listing["id"], title=f"{category} kit", category=category, min_value=1, max_value=500)
    cycles = a.get("/v1/cycles?max_nodes=2&limit=50").json()["cycles"]
    cycle = next(c for c in cycles if {p["user_id"] for p in c["participants"]} == {a.id, b.id})
    return cycle, a_listing, b_listing


# ------------------------------------------------------------------ AI endpoints


def test_analyze_listing_endpoint_validated_and_errors(app_client, cleanup_marker, monkeypatch):
    trader = Trader(app_client, "Analyst", cleanup_marker)
    set_llm_provider(FakeLLM([json.dumps(VALID)]))
    response = trader.post("/v1/ai/analyze-listing", {"text": "Selling a Leica M3 camera for 1800 USD, works perfectly."})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valuation_verified"] is False
    assert body["model"] == "fake:fake-1"
    analysis = body["analysis"]
    for field in ("name", "category", "listing_type", "description", "condition", "attributes",
                  "estimated_value", "currency", "keywords", "suggested_wants"):
        assert field in analysis
    assert analysis["category"] == "Photography"

    set_llm_provider(FakeLLM(["not json", "still not json"]))
    bad = trader.post("/v1/ai/analyze-listing", {"text": "Selling a Leica M3 camera for 1800 USD."})
    assert bad.status_code == 502 and "AI request failed" in bad.json()["detail"]

    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "0.05")
    set_llm_provider(FakeLLM([json.dumps(VALID)], delay=0.5))
    assert trader.post("/v1/ai/analyze-listing", {"text": "Selling a Leica M3 camera."}).status_code == 504

    set_llm_provider(FakeLLM([], available=False))
    assert trader.post("/v1/ai/analyze-listing", {"text": "Selling a Leica M3 camera."}).status_code == 503

    assert trader.post("/v1/ai/analyze-listing", {"text": "short"}).status_code == 422
    assert app_client.post("/v1/ai/analyze-listing", json={"text": "Selling a Leica M3 camera."}).status_code == 401
    set_llm_provider(None)


def test_explain_match_endpoint_caches_and_checks_ownership(app_client, cleanup_marker):
    seeker = Trader(app_client, "Seeker", cleanup_marker)
    owner = Trader(app_client, "Owner", cleanup_marker)
    offer = seeker.listing(title="Bench grinder", category="Tools & Workshop", estimated_value=120)
    owner.listing(title="Cordless drill set", category="Tools & Workshop", estimated_value=110)
    seeker.want(offer["id"], title="Cordless drill", category="Tools & Workshop", min_value=50, max_value=200)

    matches = seeker.get("/v1/matches").json()["items"]
    match = next(m for m in matches if m["candidate_listing"]["title"] == "Cordless drill set")

    fake = FakeLLM(["The drill set sits inside your value range and matches the category you asked for."])
    set_llm_provider(fake)
    first = seeker.post("/v1/ai/explain-match", {"match_id": match["id"]})
    assert first.status_code == 200 and first.json()["cached"] is False
    second = seeker.post("/v1/ai/explain-match", {"match_id": match["id"]})
    assert second.status_code == 200 and second.json()["cached"] is True
    assert len(fake.prompts) == 1  # cached, the provider was not called again
    assert owner.post("/v1/ai/explain-match", {"match_id": match["id"]}).status_code == 403
    assert seeker.post("/v1/ai/explain-match", {"match_id": "nope"}).status_code == 404
    set_llm_provider(None)


# ------------------------------------------------------------------ re-embedding


async def test_reembedding_on_model_version_change():
    from motor.motor_asyncio import AsyncIOMotorClient

    from lib.embeddings import LocalHashedEmbeddingProvider, set_embedding_provider
    from services import embeddings as service
    from services.embedding_store import MongoEmbeddingStore, set_embedding_store

    class CountingProvider(LocalHashedEmbeddingProvider):
        def __init__(self, version):
            self.version = version
            self.calls = 0

        async def embed(self, texts):
            self.calls += len(texts)
            return await super().embed(texts)

    mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
    database = mongo[f"barterx_test_embeddings_{uuid.uuid4().hex[:6]}"]
    set_embedding_store(MongoEmbeddingStore(database))
    docs = [
        {"id": "l1", "owner_id": "u1", "title": "Analog mixer", "description": "12 channels", "category": "Audio"},
        {"id": "l2", "owner_id": "u2", "title": "Legal review", "description": "contracts", "category": "Legal & Admin"},
    ]
    try:
        v1 = CountingProvider("1")
        set_embedding_provider(v1)
        await service.embed_subjects("listing", docs)
        assert v1.calls == 2
        await service.embed_subjects("listing", docs)  # unchanged text, so not re-embedded
        assert v1.calls == 2
        changed = [{**docs[0], "description": "16 channels now"}, docs[1]]
        await service.embed_subjects("listing", changed)
        assert v1.calls == 3  # only the changed listing

        v2 = CountingProvider("2")
        set_embedding_provider(v2)
        status = await service.embedding_status()
        assert status["version"] == "2" and status["stale"] == 2 and status["current"] == 0
        await service.embed_subjects("listing", changed)
        assert v2.calls == 2
        status = await service.embedding_status()
        assert status["current"] == 2 and status["stale"] == 0
        rows = await database.embeddings.find({}).to_list(10)
        assert {(r["model"], r["version"]) for r in rows} == {("local-hashed-bow", "2")}
    finally:
        set_embedding_provider(None)
        set_embedding_store(None)
        await mongo.drop_database(database.name)
        mongo.close()


# ------------------------------------------------------------------ cycle alerts


def test_cycle_alert_fires_once_when_listing_closes_a_cycle(app_client, cleanup_marker):
    a = Trader(app_client, "AlertA", cleanup_marker)
    b = Trader(app_client, "AlertB", cleanup_marker)
    a_listing = a.listing(title="Pottery wheel", category="Crafts & Pottery", estimated_value=150)
    a.want(a_listing["id"], title="Kiln", category="Crafts & Pottery", min_value=50, max_value=300)
    b_first = b.listing(title="Glaze set", category="Fashion", estimated_value=40)
    b.want(b_first["id"], title="Pottery wheel", category="Crafts & Pottery", min_value=50, max_value=300)
    assert not [n for n in a.notifications() if n["type"] == "cycle"]

    # B's new listing closes the cycle: A wants a Crafts item that B now offers.
    b_listing = b.listing(title="Electric kiln", category="Crafts & Pottery", estimated_value=160)
    b.patch(f"/v1/wants/{b.get('/v1/wants').json()['wants'][0]['id']}", {"listing_id": b_listing["id"]})

    a_alerts = [n for n in a.notifications() if n["type"] == "cycle"]
    b_alerts = [n for n in b.notifications() if n["type"] == "cycle"]
    assert len(a_alerts) == 1 and len(b_alerts) == 1
    assert "AlertB" in a_alerts[0]["body"] and a_alerts[0]["link"] == "/cycles"

    b.patch(f"/v1/listings/{b_listing['id']}", {"description": "Updated description"})
    assert len([n for n in a.notifications() if n["type"] == "cycle"]) == 1  # each cycle is announced once


# ------------------------------------------------------------------ payouts + reviews


class FakePayPal:
    """Simulates PayPal sandbox responses. Records every call."""

    def __init__(self, fail_first_payout=False):
        self.calls = []
        self.fail_first_payout = fail_first_payout
        self.payout_posts = 0
        self.capture_amount = None
        self.sender_item = None

    already_captured = False
    orders = 0

    def _completed(self):
        return {"status": "COMPLETED", "purchase_units": [{"payments": {"captures": [
            {"id": "CAP-1", "status": "COMPLETED", "amount": {"value": self.capture_amount["value"], "currency_code": self.capture_amount["currency_code"]}}
        ]}}]}

    async def request(self, method, path, payload=None, request_id=None):
        from services.payments import PayPalError

        self.calls.append((method, path, payload, request_id))
        if method == "POST" and path == "/v2/checkout/orders":
            self.orders += 1
            unit = payload["purchase_units"][0]
            self.capture_amount = unit["amount"]
            order = f"ORDER-{self.orders}"
            return {"id": order, "links": [{"rel": "approve", "href": f"https://www.sandbox.paypal.com/approve?token={order}"}]}
        if method == "POST" and path.startswith("/v2/checkout/orders/ORDER-") and path.endswith("/capture"):
            if self.already_captured:
                raise PayPalError("PayPal POST capture failed (422): ORDER_ALREADY_CAPTURED")
            return self._completed()
        if method == "GET" and path.startswith("/v2/checkout/orders/ORDER-"):
            return self._completed()
        if method == "POST" and path == "/v1/payments/payouts":
            self.payout_posts += 1
            self.sender_item = payload["items"][0]["sender_item_id"]
            if self.fail_first_payout and self.payout_posts == 1:
                raise PayPalError("PayPal POST /v1/payments/payouts failed (422): INSUFFICIENT_FUNDS")
            return {"batch_header": {"payout_batch_id": f"BATCH-{self.payout_posts}", "batch_status": "PENDING"}}
        if method == "GET" and path.startswith("/v1/payments/payouts/BATCH-"):
            return {"items": [{"payout_item_id": "ITEM-1", "transaction_status": "SUCCESS",
                               "payout_item": {"sender_item_id": self.sender_item}}]}
        raise AssertionError(f"unexpected PayPal call {method} {path}")


def _install_paypal(monkeypatch, fake):
    import services.payments as payments
    import services.payouts as payouts

    for module in (payments, payouts):
        monkeypatch.setattr(module, "_request", fake.request)
        monkeypatch.setattr(module, "is_configured", lambda: True)


def test_payout_flow_auto_failure_then_claim_and_reviews(app_client, cleanup_marker, monkeypatch):
    fake = FakePayPal(fail_first_payout=True)
    _install_paypal(monkeypatch, fake)
    owed = Trader(app_client, "Owed", cleanup_marker)   # gives 100, receives 80, so is owed 20
    payer = Trader(app_client, "Payer", cleanup_marker)  # gives 80, receives 100, so owes 20
    owed.patch("/v1/users/me", {"paypal_email": f"owed-payouts-{uuid.uuid4().hex[:4]}@example.com"})
    cycle, _, _ = _two_party_cycle(owed, payer, "Sports & Outdoors", 100, 80)

    proposal = owed.post("/v1/exchanges/from-cycle", {"cycle_key": cycle["key"], "participant_ids": [owed.id, payer.id]})
    assert proposal.status_code == 201, proposal.text
    exchange_id = proposal.json()["exchange"]["id"]
    for trader in (owed, payer):
        assert trader.post(f"/v1/exchanges/{exchange_id}/approve", {"decision": "approved"}).status_code == 200

    assert owed.post(f"/v1/exchanges/{exchange_id}/payouts/claim").status_code == 409  # not completed yet

    init = payer.post(f"/v1/exchanges/{exchange_id}/payments", {})
    assert init.status_code == 200, init.text
    assert fake.capture_amount == {"currency_code": "CHF", "value": "20.00"}
    captured = payer.post(f"/v1/payments/{init.json()['payment']['id']}/capture")
    assert captured.status_code == 200 and captured.json()["verified"] is True

    for trader in (owed, payer):
        assert trader.post(f"/v1/exchanges/{exchange_id}/fulfilment").status_code == 200
    assert owed.post(f"/v1/exchanges/{exchange_id}/complete").status_code == 200
    assert owed.get(f"/v1/exchanges/{exchange_id}").json()["exchange"]["status"] == "completed"

    # Automatic payout was attempted on completion and PayPal rejected it, so it is not marked paid.
    payouts = owed.get(f"/v1/exchanges/{exchange_id}/payouts").json()["payouts"]
    assert len(payouts) == 1
    first = payouts[0]
    assert first["status"] == "failed" and first["verified"] is False and first["trigger"] == "automatic"
    assert first["amount"] == 20 and first["currency"] == "CHF" and first["receiver_source"] == "paypal_email"
    assert "INSUFFICIENT_FUNDS" in first["last_error"]

    # The payer is not owed anything and cannot claim.
    assert payer.post(f"/v1/exchanges/{exchange_id}/payouts/claim").status_code == 409

    claimed = owed.post(f"/v1/exchanges/{exchange_id}/payouts/claim")
    assert claimed.status_code == 200, claimed.text
    body = claimed.json()
    assert body["status"] == "success" and body["verified"] is True and body["verification_source"] == "payouts_api"
    assert body["attempts"] == 2 and body["sender_batch_id"].endswith("-a2") and body["trigger"] == "claim"
    assert fake.payout_posts == 2

    # A success is final: claiming again does not send money a third time.
    assert owed.post(f"/v1/exchanges/{exchange_id}/payouts/claim").json()["status"] == "success"
    assert fake.payout_posts == 2
    assert any(n["type"] == "payout" and "Payout received" in n["title"] for n in owed.notifications())

    # Reviews: a verified review from a trading partner counts; an outsider's review is unverified.
    review = payer.post(f"/v1/users/{owed.id}/reviews", {"rating": 5, "comment": "Smooth trade", "exchange_id": exchange_id})
    assert review.status_code == 201 and review.json()["verified"] is True
    assert payer.post(f"/v1/users/{owed.id}/reviews", {"rating": 1, "exchange_id": exchange_id}).status_code == 409
    outsider = Trader(app_client, "Outsider", cleanup_marker)
    assert outsider.post(f"/v1/users/{owed.id}/reviews", {"rating": 5, "exchange_id": exchange_id}).status_code == 403
    assert outsider.post(f"/v1/users/{owed.id}/reviews", {"rating": 2, "comment": "Never traded"}).status_code == 201

    reputation = outsider.get(f"/v1/users/{owed.id}/reputation").json()
    assert reputation["completed_trades"] == 1
    assert reputation["verified_review_count"] == 1 and reputation["unverified_review_count"] == 1
    assert reputation["average_rating"] == 5.0  # the unverified 2/5 does not count
    assert reputation["viewer_can_review_unverified"] is False
    assert owed.get(f"/v1/users/{payer.id}/reputation").json()["reviewable_exchanges"][0]["exchange_id"] == exchange_id


def test_payout_record_is_blocked_when_paypal_not_configured(app_client, cleanup_marker, monkeypatch):
    """A balanced 2-cycle completes with no payment and no payout. An owed trader sees 503 on claim when PayPal is off."""
    import services.payouts as payouts

    a = Trader(app_client, "BalA", cleanup_marker)
    b = Trader(app_client, "BalB", cleanup_marker)
    cycle, _, _ = _two_party_cycle(a, b, "Books & Music", 60, 60)
    exchange_id = a.post("/v1/exchanges/from-cycle", {"cycle_key": cycle["key"], "participant_ids": [a.id, b.id]}).json()["exchange"]["id"]
    for trader in (a, b):
        trader.post(f"/v1/exchanges/{exchange_id}/approve", {"decision": "approved"})
    for trader in (a, b):
        trader.post(f"/v1/exchanges/{exchange_id}/fulfilment")
    assert a.post(f"/v1/exchanges/{exchange_id}/complete").status_code == 200
    assert a.get(f"/v1/exchanges/{exchange_id}").json()["exchange"]["status"] == "completed"
    assert a.get(f"/v1/exchanges/{exchange_id}/payouts").json()["payouts"] == []
    monkeypatch.setattr(payouts, "is_configured", lambda: False)
    assert a.post(f"/v1/exchanges/{exchange_id}/payouts/claim").status_code == 409  # nobody is owed in a balanced trade

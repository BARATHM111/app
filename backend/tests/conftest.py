"""Pre-scaffolded pytest fixtures for the FastAPI backend.

Tests hit the live uvicorn process managed by supervisor (not an in-process ASGI app), so
the app under test is the same one the frontend and Playwright see. Do NOT re-create this
file — add app-specific fixtures below the marker at the bottom.
"""

import os

import httpx
import pytest
import pytest_asyncio

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
API_URL = f"{BACKEND_URL}/api"


def api_url(path: str = "") -> str:
    """Absolute URL for an /api route: api_url("/status") -> http://localhost:8001/api/status."""
    return f"{API_URL}{path}"


@pytest.fixture(scope="session")
def backend_url() -> str:
    return BACKEND_URL


@pytest.fixture
def client():
    """Sync httpx client rooted at /api — the default for endpoint tests.

    Example:
        def test_status(client):
            assert client.get("/status").status_code == 200
    """
    with httpx.Client(base_url=API_URL, timeout=30.0) as c:
        yield c


@pytest_asyncio.fixture
async def aclient():
    """Async variant, for tests that also await motor/backend helpers directly."""
    async with httpx.AsyncClient(base_url=API_URL, timeout=30.0) as c:
        yield c


# --- app-specific fixtures below this line ---

TEST_EMAIL_DOMAIN = "@test.barterx.dev"


def purge_test_user_data(email_suffix: str = TEST_EMAIL_DOMAIN) -> None:
    """Remove every record owned by throwaway integration-test users (never seed/demo data)."""
    from pymongo import MongoClient
    from dotenv import load_dotenv
    from pathlib import Path

    load_dotenv(Path(__file__).parent.parent / ".env")
    mongo = MongoClient(os.environ["MONGO_URL"])
    db = mongo[os.environ["DB_NAME"]]
    users = [u["id"] for u in db.users.find({"email": {"$regex": f"{email_suffix.replace('.', '[.]')}$"}}, {"id": 1})]
    if users:
        exchanges = [e["id"] for e in db.exchanges.find({"participant_ids": {"$in": users}}, {"id": 1})]
        for name in ("exchange_participants", "exchange_approvals", "offers", "payments", "payouts", "exchange_events", "listing_reservations"):
            db[name].delete_many({"exchange_id": {"$in": exchanges}})
        db.exchanges.delete_many({"id": {"$in": exchanges}})
        listing_ids = [l["id"] for l in db.listings.find({"owner_id": {"$in": users}}, {"id": 1})]
        want_ids = [w["id"] for w in db.wants.find({"user_id": {"$in": users}}, {"id": 1})]
        db.embeddings.delete_many({"subject_id": {"$in": listing_ids + want_ids}})
        db.reviews.delete_many({"$or": [{"author_id": {"$in": users}}, {"subject_id": {"$in": users}}]})
        db.cycle_alerts.delete_many({"participant_ids": {"$in": users}})
        db.cycle_rejections.delete_many({"user_id": {"$in": users}})
        db.listings.delete_many({"owner_id": {"$in": users}})
        db.wants.delete_many({"user_id": {"$in": users}})
        db.matches.delete_many({"user_id": {"$in": users}})
        db.notifications.delete_many({"user_id": {"$in": users}})
        db.users.delete_many({"id": {"$in": users}})
    mongo.close()


@pytest.fixture
def cleanup_marker():
    """Per-test unique email suffix; that test's users and data are purged on teardown."""
    import uuid

    marker = f".{uuid.uuid4().hex[:8]}{TEST_EMAIL_DOMAIN}"
    yield marker
    purge_test_user_data(marker)


@pytest.fixture(scope="session")
def app_client():
    """In-process app (TestClient). Session-scoped so every in-process module shares one event loop."""
    from fastapi.testclient import TestClient

    import server
    from lib.ai_providers import set_llm_provider

    with TestClient(server.app, base_url="http://testserver/api") as client:
        yield client
    set_llm_provider(None)

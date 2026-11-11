"""Shared Mongo handle — import `client`/`db` from here (server.py, routers, seed.py)."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING, IndexModel

load_dotenv(Path(__file__).parent.parent / ".env")

mongo_url = os.environ["MONGO_URL"]
# Fail fast (5s) when the database is unreachable instead of hanging for the 30s driver default.
client = AsyncIOMotorClient(mongo_url, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
db = client[os.environ["DB_NAME"]]

logger = logging.getLogger(__name__)

# One entry per collection: every field a route filters, sorts, or dedupes on. Applied by ensure_indexes() at startup.
INDEXES: dict[str, list[IndexModel]] = {
    "status_checks": [IndexModel([("timestamp", DESCENDING)], name="timestamp_desc")],
    "users": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("email", ASCENDING)], name="email", unique=True),
    ],
    "listings": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("owner_id", ASCENDING), ("created_at", DESCENDING)], name="owner_created"),
        IndexModel([("owner_id", ASCENDING), ("status", ASCENDING)], name="owner_status"),
        IndexModel([("status", ASCENDING), ("type", ASCENDING), ("created_at", DESCENDING)], name="status_type_created"),
        IndexModel([("status", ASCENDING), ("category", ASCENDING)], name="status_category"),
        IndexModel([("status", ASCENDING), ("estimated_value", ASCENDING)], name="status_value"),
    ],
    "wants": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("user_id", ASCENDING), ("status", ASCENDING)], name="user_status"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("listing_id", ASCENDING)], name="listing_id", sparse=True),
    ],
    "embeddings": [
        IndexModel([("subject_kind", ASCENDING), ("subject_id", ASCENDING)], name="subject", unique=True),
        IndexModel([("subject_kind", ASCENDING), ("model", ASCENDING), ("version", ASCENDING)], name="kind_model_version"),
        IndexModel([("owner_id", ASCENDING)], name="owner"),
    ],
    "payouts": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("exchange_id", ASCENDING), ("participant_id", ASCENDING)], name="exchange_participant", unique=True),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("paypal_batch_id", ASCENDING)], name="paypal_batch", sparse=True),
    ],
    "reviews": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("author_id", ASCENDING), ("subject_id", ASCENDING), ("exchange_key", ASCENDING)], name="author_subject_exchange", unique=True),
        IndexModel([("subject_id", ASCENDING), ("verified", ASCENDING), ("created_at", DESCENDING)], name="subject_verified_created"),
    ],
    "listing_reservations": [
        IndexModel([("listing_id", ASCENDING)], name="listing_id", unique=True),
        IndexModel([("exchange_id", ASCENDING)], name="exchange_id"),
    ],
    "cycle_rejections": [
        IndexModel([("cycle_key", ASCENDING), ("user_id", ASCENDING)], name="cycle_user", unique=True),
    ],
    "cycle_alerts": [
        IndexModel([("cycle_key", ASCENDING)], name="cycle_key", unique=True),
    ],
    "matches": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("user_id", ASCENDING), ("score", DESCENDING)], name="user_score"),
        IndexModel([("want_id", ASCENDING), ("candidate_listing_id", ASCENDING)], name="want_candidate", unique=True),
    ],
    "exchanges": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)], name="status_created"),
        IndexModel([("participant_ids", ASCENDING), ("status", ASCENDING)], name="participants_status"),
    ],
    "exchange_participants": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("exchange_id", ASCENDING), ("user_id", ASCENDING)], name="exchange_user", unique=True),
        IndexModel([("exchange_id", ASCENDING), ("approval_status", ASCENDING)], name="exchange_approval"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("gives_listing_id", ASCENDING)], name="gives_listing"),
    ],
    "exchange_approvals": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("exchange_id", ASCENDING), ("created_at", DESCENDING)], name="exchange_created"),
        IndexModel([("exchange_id", ASCENDING), ("revision", ASCENDING)], name="exchange_revision"),
    ],
    "offers": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("exchange_id", ASCENDING), ("created_at", DESCENDING)], name="exchange_created"),
    ],
    "payments": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("exchange_id", ASCENDING), ("status", ASCENDING)], name="exchange_status"),
        IndexModel([("user_id", ASCENDING), ("created_at", DESCENDING)], name="user_created"),
        IndexModel([("paypal_order_id", ASCENDING)], name="paypal_order", unique=True, sparse=True),
    ],
    "notifications": [
        IndexModel([("id", ASCENDING)], name="id", unique=True),
        IndexModel([("user_id", ASCENDING), ("read", ASCENDING), ("created_at", DESCENDING)], name="user_read_created"),
    ],
}


async def ensure_indexes() -> None:
    for collection, models in INDEXES.items():
        for model in models:  # one at a time so a bad spec skips only itself
            try:
                await db[collection].create_indexes([model])
            except Exception as exc:  # never block boot on an index; the log line names what to fix
                logger.error("ensure_indexes(%s.%s): %s", collection, model.document["name"], exc)

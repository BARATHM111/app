"""Shared doc → response-model helpers so every router serialises listings identically."""

from typing import Iterable

from lib.db import db
from lib.dates import clean_doc
from models.listings import Listing, ListingBrief
from models.wants import Want


def to_listing_brief(doc: dict | None) -> ListingBrief | None:
    if not doc:
        return None
    return ListingBrief(
        id=doc["id"],
        title=doc["title"],
        type=doc["type"],
        category=doc.get("category", "Other"),
        estimated_value=float(doc["estimated_value"]),
        currency=doc.get("currency", "USD"),
    )


async def owner_map(owner_ids: Iterable[str]) -> dict:
    ids = [owner_id for owner_id in set(owner_ids) if owner_id]
    if not ids:
        return {}
    users = await db.users.find({"id": {"$in": ids}}, {"id": 1, "name": 1, "location": 1}).to_list(len(ids))
    return {user["id"]: user for user in users}


async def to_listing(doc: dict, owners: dict | None = None, locked_ids: set[str] | None = None) -> Listing:
    payload = clean_doc(dict(doc))
    owners = owners if owners is not None else await owner_map([doc["owner_id"]])
    owner = owners.get(doc["owner_id"])
    payload["owner"] = (
        {"id": owner["id"], "name": owner["name"], "location": owner.get("location", "")} if owner else None
    )
    payload["in_active_exchange"] = bool(locked_ids and doc["id"] in locked_ids)
    payload.pop("ai_extracted", None)
    return Listing(**payload)


async def to_want(doc: dict, listings: dict | None = None) -> Want:
    payload = clean_doc(dict(doc))
    payload["offered_listing"] = None
    if doc.get("listing_id"):
        listings = listings if listings is not None else {}
        offered = listings.get(doc["listing_id"])
        if offered is None:
            offered = await db.listings.find_one({"id": doc["listing_id"]})
        payload["offered_listing"] = to_listing_brief(offered)
    return Want(**payload)

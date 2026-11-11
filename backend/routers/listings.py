"""ListingsModule — CRUD for physical goods and professional services."""

import logging
import math
import re
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status as http_status

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.deps import get_current_user, get_optional_user
from lib.log import log_event
from models.common import ListingStatus, ListingType, MessageResponse
from models.listings import Listing, ListingCreate, ListingPage, ListingUpdate
from services.compatibility import ACTIVE_EXCHANGE_STATUSES
from services.cycle_alerts import after_listing_change
from services.embeddings import delete_embedding, embed_listing
from services.matching import _locked_listing_ids
from services.serializers import owner_map, to_listing

router = APIRouter(prefix="/v1/listings", tags=["listings"])
logger = logging.getLogger("barterx.listings")

SORT_OPTIONS = {
    "recent": [("created_at", -1)],
    "oldest": [("created_at", 1)],
    "value_asc": [("estimated_value", 1)],
    "value_desc": [("estimated_value", -1)],
}


def _build_filter(
    *,
    type: Optional[str],
    category: Optional[str],
    status: Optional[str],
    owner_id: Optional[str],
    q: Optional[str],
    min_value: Optional[float],
    max_value: Optional[float],
) -> dict:
    filters: dict = {}
    if type:
        filters["type"] = type
    if category:
        filters["category"] = category
    if status:
        filters["status"] = status
    if owner_id:
        filters["owner_id"] = owner_id
    if min_value is not None or max_value is not None:
        value_range: dict = {}
        if min_value is not None:
            value_range["$gte"] = min_value
        if max_value is not None:
            value_range["$lte"] = max_value
        filters["estimated_value"] = value_range
    if q:
        pattern = re.escape(q.strip())
        filters["$or"] = [
            {"title": {"$regex": pattern, "$options": "i"}},
            {"description": {"$regex": pattern, "$options": "i"}},
            {"tags": {"$regex": pattern, "$options": "i"}},
            {"category": {"$regex": pattern, "$options": "i"}},
        ]
    return filters


@router.get("", response_model=ListingPage)
async def list_listings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=12, ge=1, le=60),
    type: Optional[ListingType] = None,
    category: Optional[str] = None,
    status: Optional[ListingStatus] = None,
    owner_id: Optional[str] = None,
    q: Optional[str] = Query(default=None, max_length=120),
    min_value: Optional[float] = Query(default=None, ge=0),
    max_value: Optional[float] = Query(default=None, ge=0),
    sort: str = Query(default="recent"),
    mine: bool = False,
    user: Optional[dict] = Depends(get_optional_user),
):
    if mine and not user:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if sort not in SORT_OPTIONS:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"sort must be one of: {', '.join(SORT_OPTIONS)}",
        )

    filters = _build_filter(
        type=type.value if type else None,
        category=category,
        status=status.value if status else ("active" if not mine else None),
        owner_id=user["id"] if mine else owner_id,
        q=q,
        min_value=min_value,
        max_value=max_value,
    )
    total = await db.listings.count_documents(filters)
    cursor = (
        db.listings.find(filters)
        .sort(SORT_OPTIONS[sort])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(page_size)
    owners = await owner_map(doc["owner_id"] for doc in docs)
    locked = await _locked_listing_ids()
    items = [await to_listing(doc, owners, locked) for doc in docs]
    return ListingPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/mine", response_model=ListingPage)
async def list_my_listings(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=60),
    status: Optional[ListingStatus] = None,
    user: dict = Depends(get_current_user),
):
    filters: dict = {"owner_id": user["id"]}
    if status:
        filters["status"] = status.value
    total = await db.listings.count_documents(filters)
    docs = (
        await db.listings.find(filters)
        .sort([("created_at", -1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list(page_size)
    )
    owners = await owner_map([user["id"]])
    locked = await _locked_listing_ids()
    return ListingPage(
        items=[await to_listing(doc, owners, locked) for doc in docs],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/meta/categories", response_model=list[str])
async def list_categories():
    categories = await db.listings.distinct("category", {"status": "active"})
    return sorted(category for category in categories if category)


@router.post("", response_model=Listing, status_code=http_status.HTTP_201_CREATED)
async def create_listing(payload: ListingCreate, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    now = utc_now()
    doc = {
        "id": f"lst_{user['id']}_{int(now.timestamp() * 1000)}",
        "owner_id": user["id"],
        **payload.model_dump(mode="json"),
        "created_at": now,
        "updated_at": now,
    }
    await db.listings.insert_one(dict(doc))
    await embed_listing(doc)  # failures are logged and retried by reembed, never block the write
    background.add_task(after_listing_change, doc, created=True)
    log_event(logger, "listing.created", listing_id=doc["id"], user_id=user["id"], type=doc["type"])
    owners = await owner_map([user["id"]])
    return await to_listing(doc, owners, set())


@router.get("/{listing_id}", response_model=Listing)
async def read_listing(listing_id: str):
    doc = await db.listings.find_one({"id": listing_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Listing not found")
    locked = await _locked_listing_ids()
    return await to_listing(doc, await owner_map([doc["owner_id"]]), locked)


@router.patch("/{listing_id}", response_model=Listing)
async def update_listing(
    listing_id: str, payload: ListingUpdate, background: BackgroundTasks, user: dict = Depends(get_current_user)
):
    doc = await db.listings.find_one({"id": listing_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if doc["owner_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You do not own this listing")

    updates = {key: value for key, value in payload.model_dump(exclude_unset=True, mode="json").items() if value is not None}
    if not updates:
        return await to_listing(doc, await owner_map([doc["owner_id"]]), set())

    locked = await _locked_listing_ids()
    if listing_id in locked:
        # Re-pricing a listing mid-negotiation would silently rewrite agreed terms.
        if "estimated_value" in updates and float(updates["estimated_value"]) != float(doc["estimated_value"]):
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="This listing is committed to an active exchange — its value cannot change until that resolves",
            )
        if updates.get("status") in ("paused", "archived", "traded"):
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="This listing is committed to an active exchange and cannot be taken off the market",
            )

    updates["updated_at"] = utc_now()
    await db.listings.update_one({"id": listing_id}, {"$set": updates})
    updated = await db.listings.find_one({"id": listing_id})
    await embed_listing(updated)
    background.add_task(after_listing_change, updated, created=False)
    log_event(logger, "listing.updated", listing_id=listing_id, user_id=user["id"], fields=list(updates))
    return await to_listing(updated, await owner_map([updated["owner_id"]]), locked)


@router.delete("/{listing_id}", response_model=MessageResponse)
async def delete_listing(listing_id: str, user: dict = Depends(get_current_user)):
    doc = await db.listings.find_one({"id": listing_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if doc["owner_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You do not own this listing")
    active = await db.exchange_participants.find_one({"gives_listing_id": listing_id})
    if active:
        exchange = await db.exchanges.find_one(
            {"id": active["exchange_id"], "status": {"$in": list(ACTIVE_EXCHANGE_STATUSES)}}
        )
        if exchange:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="This listing is committed to an active exchange — cancel that exchange first",
            )
    await db.listings.delete_one({"id": listing_id})
    await delete_embedding("listing", listing_id)
    log_event(logger, "listing.deleted", listing_id=listing_id, user_id=user["id"])
    return MessageResponse(message="Listing deleted")

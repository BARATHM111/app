"""WantsModule — what a trader asks for in return, plus the listing they put up."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status as http_status

from lib.db import db
from lib.dates import utc_now
from lib.deps import get_current_user
from lib.log import log_event
from models.common import MessageResponse, WantStatus
from models.wants import Want, WantCreate, WantListResponse, WantUpdate
from services.matching import _locked_listing_ids
from services.serializers import to_listing_brief, to_want

from services.cycle_alerts import after_want_change
from services.embeddings import delete_embedding, embed_want

router = APIRouter(prefix="/v1/wants", tags=["wants"])
logger = logging.getLogger("barterx.wants")


async def _require_owned_listing(listing_id: str | None, user: dict) -> None:
    if not listing_id:
        return
    listing = await db.listings.find_one({"id": listing_id})
    if not listing:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Offered listing not found")
    if listing["owner_id"] != user["id"]:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="You can only offer your own listing in a want",
        )
    locked = await _locked_listing_ids()
    if listing_id in locked:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="That listing is already committed to an active exchange",
        )


async def _listing_options(user: dict) -> list:
    listings = await db.listings.find({"owner_id": user["id"], "status": "active"}).to_list(100)
    locked = await _locked_listing_ids()
    return [brief for brief in (to_listing_brief(doc) for doc in listings if doc["id"] not in locked) if brief]


@router.get("", response_model=WantListResponse)
async def list_wants(user: dict = Depends(get_current_user)):
    docs = await db.wants.find({"user_id": user["id"]}).sort([("created_at", -1)]).to_list(200)
    wants = [await to_want(doc) for doc in docs]
    return WantListResponse(wants=wants, listing_options=await _listing_options(user))


@router.post("", response_model=Want, status_code=http_status.HTTP_201_CREATED)
async def create_want(payload: WantCreate, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    await _require_owned_listing(payload.listing_id, user)
    now = utc_now()
    doc = {
        "id": f"wnt_{user['id']}_{int(now.timestamp() * 1000)}",
        "user_id": user["id"],
        **payload.model_dump(mode="json"),
        "status": WantStatus.open.value,
        "created_at": now,
        "updated_at": now,
    }
    await db.wants.insert_one(dict(doc))
    await embed_want(doc)
    background.add_task(after_want_change, doc)
    log_event(logger, "want.created", want_id=doc["id"], user_id=user["id"])
    return await to_want(doc)


async def _owned_want(want_id: str, user: dict) -> dict:
    doc = await db.wants.find_one({"id": want_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Want not found")
    if doc["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You do not own this want")
    return doc


@router.get("/{want_id}", response_model=Want)
async def read_want(want_id: str, user: dict = Depends(get_current_user)):
    return await to_want(await _owned_want(want_id, user))


@router.patch("/{want_id}", response_model=Want)
async def update_want(
    want_id: str, payload: WantUpdate, background: BackgroundTasks, user: dict = Depends(get_current_user)
):
    doc = await _owned_want(want_id, user)
    updates = {key: value for key, value in payload.model_dump(exclude_unset=True, mode="json").items() if value is not None}
    if "listing_id" in updates:
        await _require_owned_listing(updates["listing_id"], user)

    merged_min = float(updates.get("min_value", doc["min_value"]))
    merged_max = float(updates.get("max_value", doc["max_value"]))
    if merged_max < merged_min:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="max_value must be greater than or equal to min_value",
        )
    if not updates:
        return await to_want(doc)

    updates["updated_at"] = utc_now()
    await db.wants.update_one({"id": want_id}, {"$set": updates})
    updated = await db.wants.find_one({"id": want_id})
    await embed_want(updated)
    background.add_task(after_want_change, updated)
    log_event(logger, "want.updated", want_id=want_id, user_id=user["id"], fields=list(updates))
    return await to_want(updated)


@router.delete("/{want_id}", response_model=MessageResponse)
async def delete_want(want_id: str, user: dict = Depends(get_current_user)):
    await _owned_want(want_id, user)
    await db.wants.delete_one({"id": want_id})
    await db.matches.delete_many({"want_id": want_id})
    await delete_embedding("want", want_id)
    log_event(logger, "want.deleted", want_id=want_id, user_id=user["id"])
    return MessageResponse(message="Want deleted")

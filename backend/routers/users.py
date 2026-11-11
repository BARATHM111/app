"""UsersModule — profile management and public trader profiles."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.deps import get_current_user
from lib.log import log_event
from models.listings import ListingBrief
from models.users import UserMe, UserPublic, UserUpdate

router = APIRouter(prefix="/v1/users", tags=["users"])
logger = logging.getLogger("barterx.users")


@router.get("/me", response_model=UserMe)
async def read_profile(user: dict = Depends(get_current_user)):
    payload = clean_doc(dict(user))
    payload.pop("password_hash", None)
    return UserMe(**payload)


@router.patch("/me", response_model=UserMe)
async def update_profile(payload: UserUpdate, user: dict = Depends(get_current_user)):
    updates = {key: value for key, value in payload.model_dump(exclude_unset=True).items() if value is not None}
    if "paypal_email" in updates:
        updates["paypal_email"] = (str(updates["paypal_email"]).strip().lower() or None)
    if updates:
        updates["updated_at"] = utc_now()
        await db.users.update_one({"id": user["id"]}, {"$set": updates})
        log_event(logger, "user.updated", user_id=user["id"], fields=list(updates))
    updated = await db.users.find_one({"id": user["id"]})
    doc = clean_doc(dict(updated))
    doc.pop("password_hash", None)
    return UserMe(**doc)


@router.get("/{user_id}", response_model=UserPublic)
async def read_public_profile(user_id: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Trader not found")
    payload = clean_doc(dict(user))
    payload.pop("password_hash", None)
    payload.pop("email", None)
    return UserPublic(**payload)


@router.get("/{user_id}/listings", response_model=list[ListingBrief])
async def read_public_listings(user_id: str):
    listings = await db.listings.find({"owner_id": user_id, "status": "active"}).to_list(50)
    return [
        ListingBrief(
            id=listing["id"],
            title=listing["title"],
            type=listing["type"],
            category=listing.get("category", "Other"),
            estimated_value=float(listing["estimated_value"]),
            currency=listing.get("currency", "USD"),
        )
        for listing in listings
    ]

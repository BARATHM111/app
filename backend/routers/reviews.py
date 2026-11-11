"""Trader reputation: completed-trade count plus reviews.

- Verified review: the author and subject were both participants in that completed
  exchange. One per partner per exchange. Only these count toward the rating.
- Unverified review: any signed-in trader except the subject. One per author per subject.
  Shown and labelled as unverified, but never counted in the rating.
"""

import logging
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from pymongo.errors import DuplicateKeyError

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.deps import get_current_user, get_optional_user
from lib.log import log_event
from models.common import NotificationType
from models.reviews import Reputation, Review, ReviewableExchange, ReviewCreate
from models.users import UserBrief
from services.notifications import notify

router = APIRouter(prefix="/v1/users", tags=["reviews"])
logger = logging.getLogger("barterx.reviews")
UNVERIFIED_KEY = "unverified"


async def _shared_completed_exchanges(viewer_id: str, subject_id: str) -> List[dict]:
    return await db.exchanges.find(
        {"status": "completed", "participant_ids": {"$all": [viewer_id, subject_id]}}
    ).sort([("completed_at", -1)]).to_list(50)


def _to_review(doc: dict, authors: dict) -> Review:
    payload = clean_doc(dict(doc))
    author = authors.get(doc["author_id"])
    payload["author"] = UserBrief(id=author["id"], name=author["name"], location=author.get("location", "")) if author else None
    return Review(**payload)


@router.get("/{user_id}/reputation", response_model=Reputation)
async def read_reputation(user_id: str, viewer: Optional[dict] = Depends(get_optional_user)):
    subject = await db.users.find_one({"id": user_id}, {"id": 1, "name": 1})
    if not subject:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Trader not found")

    completed = await db.exchanges.count_documents({"status": "completed", "participant_ids": user_id})
    docs = await db.reviews.find({"subject_id": user_id}).sort([("verified", -1), ("created_at", -1)]).to_list(100)
    authors = {
        row["id"]: row
        for row in await db.users.find({"id": {"$in": list({d["author_id"] for d in docs})}}, {"id": 1, "name": 1, "location": 1}).to_list(100)
    }
    verified = [d for d in docs if d.get("verified")]
    average = round(sum(d["rating"] for d in verified) / len(verified), 2) if verified else None

    reviewable: List[ReviewableExchange] = []
    can_unverified = False
    if viewer and viewer["id"] != user_id:
        reviewed = {d.get("exchange_id") for d in docs if d["author_id"] == viewer["id"] and d.get("verified")}
        for exchange in await _shared_completed_exchanges(viewer["id"], user_id):
            if exchange["id"] not in reviewed:
                reviewable.append(
                    ReviewableExchange(
                        exchange_id=exchange["id"],
                        cycle_type=exchange.get("cycle_type", 2),
                        completed_at=clean_doc({"created_at": exchange.get("completed_at")})["created_at"],
                    )
                )
        can_unverified = not any(d["author_id"] == viewer["id"] and not d.get("verified") for d in docs)

    return Reputation(
        user_id=user_id,
        name=subject["name"],
        completed_trades=completed,
        verified_review_count=len(verified),
        unverified_review_count=len(docs) - len(verified),
        average_rating=average,
        reviews=[_to_review(d, authors) for d in docs],
        reviewable_exchanges=reviewable,
        viewer_can_review_unverified=can_unverified,
    )


@router.post("/{user_id}/reviews", response_model=Review, status_code=http_status.HTTP_201_CREATED)
async def create_review(user_id: str, payload: ReviewCreate, user: dict = Depends(get_current_user)):
    if user_id == user["id"]:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="You cannot review yourself")
    subject = await db.users.find_one({"id": user_id}, {"id": 1})
    if not subject:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Trader not found")

    verified = False
    if payload.exchange_id:
        exchange = await db.exchanges.find_one({"id": payload.exchange_id})
        if not exchange:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
        if not {user["id"], user_id}.issubset(set(exchange.get("participant_ids") or [])):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="A verified review needs both of you to be participants in that exchange",
            )
        if exchange.get("status") != "completed":
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="You can leave a verified review once the exchange is completed",
            )
        verified = True

    now = utc_now()
    doc = {
        "id": f"rev_{uuid4().hex[:12]}",
        "author_id": user["id"],
        "subject_id": user_id,
        "exchange_id": payload.exchange_id if verified else None,
        "exchange_key": payload.exchange_id if verified else UNVERIFIED_KEY,
        "rating": payload.rating,
        "comment": payload.comment.strip(),
        "verified": verified,
        "created_at": now,
        "updated_at": now,
    }
    try:
        await db.reviews.insert_one(dict(doc))
    except DuplicateKeyError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                "You already reviewed this trader for that exchange"
                if verified
                else "You already left an unverified review for this trader"
            ),
        ) from exc

    await notify(
        user_id,
        NotificationType.review,
        f"New {'verified ' if verified else ''}review: {payload.rating}/5",
        f"{user['name']} left you a review{' for a completed trade' if verified else ' (unverified)'}.",
        f"/trader/{user_id}",
    )
    log_event(logger, "review.created", author_id=user["id"], subject_id=user_id, verified=verified)
    return _to_review(doc, {user["id"]: user})

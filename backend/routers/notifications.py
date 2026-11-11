"""NotificationsModule — the per-user activity feed."""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.deps import get_current_user
from models.common import MessageResponse
from models.notifications import Notification, NotificationPage, UnreadCountResponse

router = APIRouter(prefix="/v1/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage)
async def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_user),
):
    filters = {"user_id": user["id"]}
    total = await db.notifications.count_documents(filters)
    docs = (
        await db.notifications.find(filters)
        .sort([("created_at", -1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list(page_size)
    )
    return NotificationPage(
        items=[Notification(**clean_doc(dict(doc))) for doc in docs],
        total=total,
        page=page,
        page_size=page_size,
        pages=max(1, math.ceil(total / page_size)),
    )


@router.get("/unread", response_model=UnreadCountResponse)
async def unread_notifications(user: dict = Depends(get_current_user)):
    unread = await db.notifications.count_documents({"user_id": user["id"], "read": False})
    docs = (
        await db.notifications.find({"user_id": user["id"], "read": False})
        .sort([("created_at", -1)])
        .limit(10)
        .to_list(10)
    )
    return UnreadCountResponse(
        unread=unread, items=[Notification(**clean_doc(dict(doc))) for doc in docs]
    )


@router.post("/{notification_id}/read", response_model=Notification)
async def mark_read(notification_id: str, user: dict = Depends(get_current_user)):
    doc = await db.notifications.find_one({"id": notification_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if doc["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="This notification is not yours")
    await db.notifications.update_one({"id": notification_id}, {"$set": {"read": True, "updated_at": utc_now()}})
    updated = await db.notifications.find_one({"id": notification_id})
    return Notification(**clean_doc(dict(updated)))


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(user: dict = Depends(get_current_user)):
    result = await db.notifications.update_many(
        {"user_id": user["id"], "read": False}, {"$set": {"read": True, "updated_at": utc_now()}}
    )
    return MessageResponse(message=f"Marked {result.modified_count} notifications as read")

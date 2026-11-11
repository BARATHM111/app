"""Notification fan-out — one small helper so every module notifies the same way."""

from uuid import uuid4

from lib.db import db
from lib.dates import utc_now
from models.common import NotificationType


async def notify(
    user_id: str,
    notification_type: NotificationType,
    title: str,
    body: str = "",
    link: str = "",
) -> dict:
    doc = {
        "id": str(uuid4()),
        "user_id": user_id,
        "type": notification_type.value,
        "title": title,
        "body": body,
        "link": link,
        "read": False,
        "created_at": utc_now(),
    }
    await db.notifications.insert_one(dict(doc))
    return doc


async def notify_many(user_ids: list[str], notification_type: NotificationType, title: str, body: str = "", link: str = "") -> None:
    for user_id in user_ids:
        await notify(user_id, notification_type, title, body, link)

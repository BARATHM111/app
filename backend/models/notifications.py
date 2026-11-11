"""Notification models."""

from datetime import datetime
from typing import List

from pydantic import BaseModel, Field

from models.common import NotificationType, Page


class Notification(BaseModel):
    id: str
    user_id: str
    type: NotificationType
    title: str
    body: str = ""
    link: str = ""
    read: bool = False
    created_at: datetime


NotificationPage = Page[Notification]


class UnreadCountResponse(BaseModel):
    unread: int = 0
    items: List[Notification] = Field(default_factory=list)

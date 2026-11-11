"""Listing models — physical goods and professional services share one shape."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from models.common import ListingStatus, ListingType, Page
from models.users import UserBrief


class ListingCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    type: ListingType
    category: str = Field(default="Other", max_length=80)
    condition: str = Field(default="", max_length=80)
    estimated_value: float = Field(gt=0, le=1_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    tags: List[str] = Field(default_factory=list)
    location: str = Field(default="", max_length=120)
    status: ListingStatus = ListingStatus.active
    ai_assisted: bool = False


class ListingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    type: ListingType | None = None
    category: str | None = Field(default=None, max_length=80)
    condition: str | None = Field(default=None, max_length=80)
    estimated_value: float | None = Field(default=None, gt=0, le=1_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    tags: List[str] | None = None
    location: str | None = Field(default=None, max_length=120)
    status: ListingStatus | None = None


class Listing(BaseModel):
    id: str
    owner_id: str
    owner: Optional[UserBrief] = None
    title: str
    description: str = ""
    type: ListingType
    category: str = "Other"
    condition: str = ""
    estimated_value: float
    currency: str = "USD"
    tags: List[str] = Field(default_factory=list)
    location: str = ""
    status: ListingStatus = ListingStatus.active
    ai_assisted: bool = False
    # True while the listing sits in a non-terminal exchange — such listings are
    # never reserved by a second conflicting exchange.
    in_active_exchange: bool = False
    created_at: datetime
    updated_at: datetime


class ListingBrief(BaseModel):
    id: str
    title: str
    type: ListingType
    category: str = "Other"
    estimated_value: float
    currency: str = "USD"


ListingPage = Page[Listing]

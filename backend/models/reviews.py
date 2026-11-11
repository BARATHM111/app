"""Review and reputation models."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from models.users import UserBrief


class ReviewCreate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)
    exchange_id: Optional[str] = Field(
        default=None,
        description="A completed exchange you shared with this trader. Including it makes the review verified.",
    )


class Review(BaseModel):
    id: str
    author: Optional[UserBrief] = None
    subject_id: str
    exchange_id: Optional[str] = None
    rating: int
    comment: str = ""
    verified: bool = False
    created_at: datetime


class ReviewableExchange(BaseModel):
    exchange_id: str
    cycle_type: int
    completed_at: Optional[datetime] = None


class Reputation(BaseModel):
    user_id: str
    name: str
    completed_trades: int = 0
    verified_review_count: int = 0
    unverified_review_count: int = 0
    average_rating: Optional[float] = None  # verified reviews only
    reviews: List[Review] = Field(default_factory=list)
    # Completed exchanges the *viewer* shared with this trader and has not reviewed yet.
    reviewable_exchanges: List[ReviewableExchange] = Field(default_factory=list)
    viewer_can_review_unverified: bool = False
    note: str = "Only reviews from verified trades count toward the rating."

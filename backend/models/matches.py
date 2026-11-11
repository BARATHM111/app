"""Match models — semantic candidates plus the deterministic reasons behind them."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from models.common import Page
from models.listings import ListingBrief
from models.wants import Want


class Match(BaseModel):
    id: str
    user_id: str
    want_id: str
    candidate_listing_id: str
    candidate_listing: Optional[ListingBrief] = None
    offered_listing: Optional[ListingBrief] = None
    score: float
    semantic_score: float
    value_score: float
    category_score: float = 0.0
    location_score: float = 0.0
    compatible: bool
    reasons: List[str] = Field(default_factory=list)
    explanation: Optional[str] = None
    explanation_generated_at: Optional[datetime] = None
    dismissed: bool = False
    created_at: datetime


MatchPage = Page[Match]


class MatchExplanationRequest(BaseModel):
    match_id: str = Field(min_length=1)


class MatchExplanationResponse(BaseModel):
    match_id: str
    explanation: str
    generated_at: datetime
    model: str
    cached: bool = False

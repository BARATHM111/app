"""Want models — what a trader asks for in return, optionally tied to a listing they offer."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from models.common import ListingType, WantStatus
from models.listings import ListingBrief


class WantCreate(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=4000)
    category: str = Field(default="", max_length=80)
    # "any" means the trader accepts either goods or a service.
    target_type: str = Field(default="any", pattern="^(goods|services|any)$")
    min_value: float = Field(ge=0, le=1_000_000)
    max_value: float = Field(gt=0, le=1_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    keywords: List[str] = Field(default_factory=list)
    # The listing this trader puts into the exchange to get the want filled.
    listing_id: Optional[str] = None
    min_condition: Optional[str] = Field(default=None, pattern="^(New|Like new|Excellent|Good|Fair|For parts)$")
    location_preference: str = Field(default="any", pattern="^(any|local)$")

    @model_validator(mode="after")
    def check_range(self) -> "WantCreate":
        if self.max_value < self.min_value:
            raise ValueError("max_value must be greater than or equal to min_value")
        return self


class WantUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    category: str | None = Field(default=None, max_length=80)
    target_type: str | None = Field(default=None, pattern="^(goods|services|any)$")
    min_value: float | None = Field(default=None, ge=0, le=1_000_000)
    max_value: float | None = Field(default=None, gt=0, le=1_000_000)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    keywords: List[str] | None = None
    listing_id: str | None = None
    status: WantStatus | None = None
    min_condition: str | None = Field(default=None, pattern="^(|New|Like new|Excellent|Good|Fair|For parts)$")
    location_preference: str | None = Field(default=None, pattern="^(any|local)$")


class Want(BaseModel):
    id: str
    user_id: str
    title: str
    description: str = ""
    category: str = ""
    target_type: str = "any"
    min_value: float
    max_value: float
    currency: str = "USD"
    keywords: List[str] = Field(default_factory=list)
    listing_id: Optional[str] = None
    offered_listing: Optional[ListingBrief] = None
    min_condition: Optional[str] = None
    location_preference: str = "any"
    status: WantStatus = WantStatus.open
    created_at: datetime
    updated_at: datetime


class GraphEdge(BaseModel):
    """Directed edge: `from_user` gives `listing` to `to_user`, satisfying a specific want of theirs."""

    from_user: str
    to_user: str
    listing_id: str
    listing_title: str
    satisfies_want_id: str
    want_title: str = ""
    value: float
    currency: str = "USD"
    semantic_score: float = 0.0
    score: float = 0.0
    components: Dict[str, float] = Field(default_factory=dict)


class CycleParticipant(BaseModel):
    user_id: str
    user_name: str
    gives_listing_id: str
    gives_listing_title: str
    gives_value: float
    receives_listing_id: str
    receives_listing_title: str
    receives_value: float
    # Positive = receives more than gives (owes the difference); negative = is owed.
    balance_amount: float
    currency: str = "USD"
    receives_via_want_id: str = ""
    receives_via_want_title: str = ""
    incoming_edge_score: float = 0.0


class Cycle(BaseModel):
    """Deterministically discovered exchange cycle. A candidate, never a guarantee."""

    key: str
    id: str = ""  # same as key; the stable cycle ID
    status: str = "discovered"
    cycle_type: int = Field(description="2 for a direct swap, 3 for a triangular cycle")
    participant_ids: List[str]
    participants: List[CycleParticipant]
    total_value: float
    total_imbalance: float  # sum of |value differences|
    mean_semantic_score: float
    min_edge_score: float = 0.0
    avg_edge_score: float = 0.0
    rank: int = 0
    reasons: List[str] = Field(default_factory=list)
    edges: List[GraphEdge]


class CycleProposalRequest(BaseModel):
    """Server re-derives every value from the listings — the client cannot inject numbers."""

    cycle_key: str
    participant_ids: List[str]


class CycleListResponse(BaseModel):
    cycles: List[Cycle]
    candidate_count: int
    generated_at: datetime


class WantListResponse(BaseModel):
    wants: List[Want]
    listing_options: List[ListingBrief] = Field(default_factory=list)

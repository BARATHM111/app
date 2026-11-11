"""Exchange models: the proposal, its participant ledger, approvals and offers."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from models.common import (
    ApprovalDecision,
    ApprovalStatus,
    ExchangeStatus,
    FulfilmentStatus,
    OfferStatus,
)
from models.listings import ListingBrief
from models.users import UserBrief


class ExchangeParticipant(BaseModel):
    id: str
    exchange_id: str
    user_id: str
    user: Optional[UserBrief] = None
    gives_listing_id: str
    gives_listing: Optional[ListingBrief] = None
    receives_listing_id: str
    receives_listing: Optional[ListingBrief] = None
    listing_value_given: Optional[float] = None  # the listing's own estimate, before negotiation
    value_given: float  # agreed value for the current revision
    value_received: float
    receives_via_want_id: str = ""
    # Positive balance = this trader received more value than they gave and owes a
    # balancing payment. Negative = they gave more and is owed the difference.
    balance_amount: float
    currency: str = "USD"
    approval_status: ApprovalStatus = ApprovalStatus.pending
    approved_revision: Optional[int] = None
    changes_note: Optional[str] = None
    fulfilment_status: FulfilmentStatus = FulfilmentStatus.pending
    fulfilled_at: Optional[datetime] = None
    created_at: datetime


class ExchangeApproval(BaseModel):
    """Append-only approval ledger. A decision only counts at the revision it was made for."""

    id: str
    exchange_id: str
    participant_id: str
    user_id: str
    revision: int
    decision: ApprovalDecision
    note: str = ""
    created_at: datetime


class Offer(BaseModel):
    id: str
    exchange_id: str
    revision: int
    from_user_id: str
    from_user_name: str = ""
    to_user_id: str
    message: str
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)
    status: OfferStatus = OfferStatus.open
    created_at: datetime


class ExchangeEvent(BaseModel):
    """Audit trail entry for one state transition or action."""

    id: str
    exchange_id: str
    actor_id: Optional[str] = None
    kind: str
    from_status: str
    to_status: str
    revision: int = 1
    note: str = ""
    created_at: datetime


class Dispute(BaseModel):
    opened_by: str
    reason: str
    opened_at: Optional[datetime] = None
    resolved_by: List[str] = Field(default_factory=list)
    resolution: Optional[Dict[str, Any]] = None


class PaymentSummary(BaseModel):
    required: int = 0
    captured: int = 0
    total_due: float = 0.0
    total_captured: float = 0.0
    currency: str = "USD"
    all_verified: bool = True


class Exchange(BaseModel):
    id: str
    cycle_type: int
    status: ExchangeStatus
    revision: int
    participant_ids: List[str]
    participants: List[ExchangeParticipant]
    currency: str = "USD"
    value_summary: Dict[str, float] = Field(default_factory=dict)
    payment_summary: PaymentSummary = Field(default_factory=PaymentSummary)
    approvals_current: int = 0
    approvals_required: int = 0
    is_participant: bool = False
    my_participant: Optional[ExchangeParticipant] = None
    cycle_key: str = ""
    revised_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None  # None = never expires
    dispute: Optional[Dispute] = None
    status_before_dispute: Optional[str] = None
    allowed_actions: List[str] = Field(default_factory=list)
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class ExchangeBrief(BaseModel):
    id: str
    cycle_type: int
    status: ExchangeStatus
    revision: int
    currency: str = "USD"
    my_role: Optional[str] = None
    my_balance: Optional[float] = None
    counterparties: List[UserBrief] = Field(default_factory=list)
    total_value: float = 0.0
    created_at: datetime
    updated_at: datetime


class ExchangeListResponse(BaseModel):
    exchanges: List[ExchangeBrief]


class ExchangeFromCycleRequest(BaseModel):
    cycle_key: str
    participant_ids: List[str] = Field(min_length=2, max_length=3)


class ApproveRequest(BaseModel):
    decision: ApprovalDecision = ApprovalDecision.approved
    note: str = Field(default="", max_length=1000)
    # The revision the participant reviewed. A mismatch means the terms changed: 409.
    revision: Optional[int] = Field(default=None, ge=1)


class CounterofferRequest(BaseModel):
    """New agreed value per listing in the exchange (listing_id -> value). Balances are re-derived server-side."""

    agreed_values: Dict[str, float] = Field(min_length=1, max_length=3)
    message: str = Field(min_length=1, max_length=2000)

    @field_validator("agreed_values")
    @classmethod
    def positive(cls, values: Dict[str, float]) -> Dict[str, float]:
        for value in values.values():
            if not (0 < float(value) <= 1_000_000):
                raise ValueError("Each agreed value must be between 0 and 1,000,000")
        return values


class ReasonRequest(BaseModel):
    reason: str = Field(default="", max_length=1000)


class DisputeRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AdminResolveRequest(BaseModel):
    action: Literal["resume", "cancel"]
    note: str = Field(min_length=3, max_length=1000)


class RequestChangesRequest(BaseModel):
    note: str = Field(min_length=1, max_length=1000)
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)


class OfferCreateRequest(BaseModel):
    to_user_id: str
    message: str = Field(min_length=1, max_length=2000)
    proposed_changes: Dict[str, Any] = Field(default_factory=dict)


class ExchangeDetail(BaseModel):
    exchange: Exchange
    approvals: List[ExchangeApproval] = Field(default_factory=list)
    offers: List[Offer] = Field(default_factory=list)
    events: List[ExchangeEvent] = Field(default_factory=list)


class FulfilmentResponse(BaseModel):
    participant: ExchangeParticipant
    exchange_status: ExchangeStatus

"""Enums and shared wrapper models used across every BarterX resource."""

from enum import Enum
from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ListingType(str, Enum):
    goods = "goods"
    services = "services"


class ListingStatus(str, Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    reserved = "reserved"
    traded = "traded"
    archived = "archived"


class WantStatus(str, Enum):
    open = "open"
    fulfilled = "fulfilled"
    closed = "closed"


class ExchangeStatus(str, Enum):
    """Lifecycle of a multi-party exchange. Payment and physical fulfilment are separate stages."""

    discovered = "discovered"                    # a cycle candidate (never stored as an exchange)
    proposed = "proposed"                        # created, no approvals for the current version yet
    pending_approval = "pending_approval"        # some, not all, approved the current version
    approved = "approved"                        # everyone approved; balancing payments not started
    payment_pending = "payment_pending"          # at least one PayPal order exists, not all verified
    ready_for_fulfillment = "ready_for_fulfillment"
    fulfillment_in_progress = "fulfillment_in_progress"
    completed = "completed"
    rejected = "rejected"
    cancelled = "cancelled"
    disputed = "disputed"
    expired = "expired"


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    changes_requested = "changes_requested"


class ApprovalDecision(str, Enum):
    approved = "approved"
    changes_requested = "changes_requested"


class FulfilmentStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"


class PaymentStatus(str, Enum):
    created = "created"
    approved = "approved"
    captured = "captured"
    failed = "failed"
    refunded = "refunded"
    cancelled = "cancelled"     # payer abandoned the PayPal approval, or terms changed before capture
    pending = "pending"         # PayPal accepted the capture but holds it (e.g. PENDING review)


class OfferStatus(str, Enum):
    open = "open"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class NotificationType(str, Enum):
    match = "match"
    cycle = "cycle"
    exchange = "exchange"
    approval = "approval"
    payment = "payment"
    fulfilment = "fulfilment"
    payout = "payout"
    review = "review"
    system = "system"


class PayoutStatus(str, Enum):
    pending = "pending"          # recorded, not yet accepted by PayPal
    processing = "processing"    # PayPal accepted the batch; item still in flight
    success = "success"          # PayPal reports the item SUCCESS (verified via API/webhook)
    unclaimed = "unclaimed"      # receiver has no PayPal account yet; PayPal holds the funds
    failed = "failed"            # PayPal rejected/returned it, or the call failed
    blocked = "blocked"          # cannot send yet (PayPal not configured, no payout email)


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int = 1
    page_size: int = 20
    pages: int = 1


class MessageResponse(BaseModel):
    message: str


class CurrencyAmount(BaseModel):
    amount: float = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)

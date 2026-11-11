"""Payout models: platform-to-trader balancing payouts for participants who are owed money."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from models.common import PayoutStatus


class Payout(BaseModel):
    id: str
    exchange_id: str
    participant_id: str
    user_id: str
    amount: float
    currency: str
    receiver_email: str
    receiver_source: str = "paypal_email"  # "paypal_email" | "login_email"
    sender_batch_id: str
    paypal_batch_id: Optional[str] = None
    paypal_item_id: Optional[str] = None
    paypal_transaction_status: Optional[str] = None
    status: PayoutStatus
    trigger: str = "automatic"  # "automatic" | "claim"
    verified: bool = False
    verification_source: Optional[str] = None
    attempts: int = 0
    last_error: Optional[str] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class PayoutListResponse(BaseModel):
    payouts: List[Payout] = Field(default_factory=list)
    note: str = (
        "Payouts are sent from the BarterX PayPal sandbox account after the exchange completes. "
        "A payout only counts as paid once PayPal confirms it."
    )

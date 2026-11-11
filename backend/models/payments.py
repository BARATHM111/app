"""Payment models. Status only ever advances from verified server-side PayPal data."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from models.common import PaymentStatus


class Payment(BaseModel):
    id: str
    exchange_id: str
    participant_id: str
    user_id: str
    amount: float = Field(ge=0)
    currency: str = "USD"
    provider: str = "paypal"
    environment: str = "sandbox"
    revision: int = 1
    paypal_order_id: Optional[str] = None
    paypal_capture_id: Optional[str] = None
    status: PaymentStatus = PaymentStatus.created
    # Never true unless PayPal itself confirmed the capture (API response or verified webhook).
    verified: bool = False
    verification_source: Optional[str] = None
    authorized_at: Optional[datetime] = None
    captured_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PaymentInitRequest(BaseModel):
    """The act of calling this endpoint is the trader's explicit authorisation to pay."""

    return_url: str | None = Field(default=None, max_length=500)
    cancel_url: str | None = Field(default=None, max_length=500)


class PaymentInitResponse(BaseModel):
    payment: Payment
    approval_url: str
    paypal_order_id: str
    environment: str = "sandbox"


class PaymentConfigStatus(BaseModel):
    configured: bool
    environment: str = "sandbox"
    detail: str
    escrow_note: str = (
        "PayPal is not an escrow service. Captured sandbox funds settle to the marketplace "
        "sandbox merchant account; the ledger records who owes what."
    )


class PaymentListResponse(BaseModel):
    payments: list[Payment]

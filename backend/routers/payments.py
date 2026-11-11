"""PaymentsModule — PayPal Sandbox balancing payments, always user-initiated and server-verified."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from lib.db import db
from lib.deps import get_current_user
from lib.log import log_event
from models.payments import (
    Payment,
    PaymentConfigStatus,
    PaymentInitRequest,
    PaymentInitResponse,
    PaymentListResponse,
)
from services import payments as payments_service
from services.exchanges import get_participant_or_403
from services.payments import (
    PayPalNotConfigured,
    capture_payment,
    config_status,
    find_payment,
    initiate_payment,
)

router = APIRouter(prefix="/v1/payments", tags=["payments"])
exchange_router = APIRouter(prefix="/v1/exchanges", tags=["payments"])
logger = logging.getLogger("barterx.payments")


@router.get("/config", response_model=PaymentConfigStatus)
async def read_config():
    return config_status()


@router.get("/mine", response_model=PaymentListResponse)
async def list_my_payments(user: dict = Depends(get_current_user)):
    docs = await db.payments.find({"user_id": user["id"]}).sort([("created_at", -1)]).to_list(100)
    payments = []
    for doc in docs:
        payments.append(await payments_service._payment_model(doc))
    return PaymentListResponse(payments=payments)


@router.get("/{payment_id}", response_model=Payment)
async def read_payment(payment_id: str, user: dict = Depends(get_current_user)):
    doc = await find_payment(payment_id)
    if doc["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="This payment is not yours")
    return await payments_service._payment_model(doc)


@router.post("/{payment_id}/cancel", response_model=Payment)
async def cancel(payment_id: str, user: dict = Depends(get_current_user)):
    payment = await payments_service.cancel_payment(payment_id, user)
    log_event(logger, "payment.cancelled", payment_id=payment_id, user_id=user["id"])
    return payment


@router.post("/{payment_id}/sync", response_model=Payment)
async def sync(payment_id: str, user: dict = Depends(get_current_user)):
    payment = await payments_service.sync_payment(payment_id, user)
    log_event(logger, "payment.synced", payment_id=payment_id, user_id=user["id"], status=payment.status.value)
    return payment


@router.post("/{payment_id}/capture", response_model=Payment)
async def capture(payment_id: str, user: dict = Depends(get_current_user)):
    payment = await capture_payment(payment_id, user)
    log_event(
        logger,
        "payment.capture_attempted",
        payment_id=payment_id,
        user_id=user["id"],
        status=payment.status.value,
        verified=payment.verified,
    )
    return payment


@exchange_router.post("/{exchange_id}/payments", response_model=PaymentInitResponse)
async def create_balance_payment(
    exchange_id: str,
    payload: PaymentInitRequest,
    user: dict = Depends(get_current_user),
):
    """Only reachable from an explicit user action — the request itself is the authorisation."""
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
    participant = await get_participant_or_403(exchange_id, user)
    if not payments_service.is_configured():
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "PayPal sandbox credentials are not configured on the backend, so no payment can be "
                "created. Nothing has been charged."
            ),
        )
    try:
        result = await initiate_payment(
            exchange,
            participant,
            user,
            return_url=payload.return_url or f"/proposal/{exchange_id}",
            cancel_url=payload.cancel_url or f"/proposal/{exchange_id}",
        )
    except PayPalNotConfigured as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except payments_service.PayPalError as exc:
        log_event(logger, "payment.order_failed", exchange_id=exchange_id, error=str(exc)[:300])
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    log_event(
        logger,
        "payment.order_created",
        exchange_id=exchange_id,
        user_id=user["id"],
        amount=result.payment.amount,
    )
    return result

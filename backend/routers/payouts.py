"""Payout endpoints: list, claim (retry) and refresh balancing payouts for owed traders."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from lib.db import db
from lib.deps import get_current_user
from lib.log import log_event
from models.payouts import Payout, PayoutListResponse
from services import payouts as payout_service
from services.exchanges import get_participant_or_403

router = APIRouter(prefix="/v1/payouts", tags=["payouts"])
exchange_router = APIRouter(prefix="/v1/exchanges", tags=["payouts"])
logger = logging.getLogger("barterx.payouts")


@router.get("/mine", response_model=PayoutListResponse)
async def my_payouts(user: dict = Depends(get_current_user)):
    docs = await db.payouts.find({"user_id": user["id"]}).sort([("created_at", -1)]).to_list(100)
    return PayoutListResponse(payouts=[payout_service._model(doc) for doc in docs])


@router.post("/{payout_id}/refresh", response_model=Payout)
async def refresh(payout_id: str, user: dict = Depends(get_current_user)):
    return await payout_service.refresh_payout(payout_id, user)


@exchange_router.get("/{exchange_id}/payouts", response_model=PayoutListResponse)
async def exchange_payouts(exchange_id: str, user: dict = Depends(get_current_user)):
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
    await get_participant_or_403(exchange_id, user)
    return PayoutListResponse(payouts=await payout_service.list_for_exchange(exchange_id))


@exchange_router.post("/{exchange_id}/payouts/claim", response_model=Payout)
async def claim(exchange_id: str, user: dict = Depends(get_current_user)):
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
    participant = await get_participant_or_403(exchange_id, user)
    payout = await payout_service.claim_payout(exchange, participant)
    log_event(logger, "payout.claimed", exchange_id=exchange_id, user_id=user["id"], status=payout.status.value)
    return payout

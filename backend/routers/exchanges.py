"""ExchangesModule: propose, approve, reject, counteroffer, cancel, fulfil, complete and dispute.

Thin HTTP layer. Every rule lives in services/exchanges.py. Every action requires the session
user to be a participant (checked there), so no one can act on another trader's behalf.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from lib.db import db
from lib.deps import get_current_user
from lib.log import log_event
from models.common import ApprovalDecision
from models.exchanges import (
    ApproveRequest,
    CounterofferRequest,
    DisputeRequest,
    ExchangeDetail,
    ExchangeFromCycleRequest,
    ExchangeListResponse,
    FulfilmentResponse,
    OfferCreateRequest,
    ReasonRequest,
    RequestChangesRequest,
)
from services import exchanges as svc
from services import graph as graph_service

router = APIRouter(prefix="/v1/exchanges", tags=["exchanges"])
logger = logging.getLogger("barterx.exchanges")


async def _load(exchange_id: str) -> dict:
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
    return exchange


async def _detail(exchange_id: str, user: dict) -> ExchangeDetail:
    await _load(exchange_id)
    is_participant = await db.exchange_participants.find_one({"exchange_id": exchange_id, "user_id": user["id"]})
    if not is_participant and user.get("role") != "admin":
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Only a participant of this exchange can view it")
    exchange = await svc.refresh_exchange_state(exchange_id, with_children=True)  # applies expiry lazily
    history = await svc.exchange_history(exchange_id)
    return ExchangeDetail(exchange=await svc.serialize_exchange(exchange, user["id"]), **history)


@router.get("", response_model=ExchangeListResponse)
async def list_my_exchanges(user: dict = Depends(get_current_user)):
    docs = await db.exchanges.find({"participant_ids": user["id"]}).sort([("updated_at", -1)]).to_list(100)
    docs = [await svc.expire_if_due(doc) for doc in docs]
    return ExchangeListResponse(exchanges=[await svc.serialize_brief(doc, user["id"]) for doc in docs])


@router.post("/from-cycle", response_model=ExchangeDetail, status_code=http_status.HTTP_201_CREATED)
async def propose_from_cycle(payload: ExchangeFromCycleRequest, user: dict = Depends(get_current_user)):
    """Proposal: re-derives the cycle from live data. The result is 'proposed', never approved."""
    cycle = await graph_service.find_cycle(payload.cycle_key)
    if not cycle or set(cycle.participant_ids) != set(payload.participant_ids):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="That cycle is no longer available. A listing or want changed, or a listing was reserved by another exchange.",
        )
    exchange_id = await svc.create_exchange_from_cycle(cycle, user)
    return await _detail(exchange_id, user)


@router.get("/{exchange_id}", response_model=ExchangeDetail)
async def read_exchange(exchange_id: str, user: dict = Depends(get_current_user)):
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/approve", response_model=ExchangeDetail)
async def approve_exchange(exchange_id: str, payload: ApproveRequest, user: dict = Depends(get_current_user)):
    exchange = await _load(exchange_id)
    if payload.decision == ApprovalDecision.changes_requested:
        if not payload.note.strip():
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tell the other participants what needs to change")
        await svc.record_decision(exchange, user, ApprovalDecision.changes_requested, payload.note.strip())
    else:
        await svc.approve(exchange, user, payload.revision, payload.note.strip())
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/reject", response_model=ExchangeDetail)
async def reject_exchange(exchange_id: str, payload: ReasonRequest, user: dict = Depends(get_current_user)):
    await svc.reject(await _load(exchange_id), user, payload.reason.strip())
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/counteroffer", response_model=ExchangeDetail)
async def counteroffer(exchange_id: str, payload: CounterofferRequest, user: dict = Depends(get_current_user)):
    await svc.counteroffer(await _load(exchange_id), user, payload.agreed_values, payload.message.strip())
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/request-changes", response_model=ExchangeDetail)
async def request_changes(exchange_id: str, payload: RequestChangesRequest, user: dict = Depends(get_current_user)):
    await svc.record_decision(await _load(exchange_id), user, ApprovalDecision.changes_requested, payload.note.strip())
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/offers", response_model=ExchangeDetail)
async def create_offer(exchange_id: str, payload: OfferCreateRequest, user: dict = Depends(get_current_user)):
    await svc.add_offer(await _load(exchange_id), user, payload.to_user_id, payload.message.strip(), payload.proposed_changes)
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/cancel", response_model=ExchangeDetail)
async def cancel(exchange_id: str, payload: ReasonRequest | None = None, user: dict = Depends(get_current_user)):
    await svc.cancel_exchange(await _load(exchange_id), user, (payload.reason if payload else "").strip())
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/fulfilment", response_model=FulfilmentResponse)
async def fulfil(exchange_id: str, user: dict = Depends(get_current_user)):
    updated = await svc.confirm_fulfilment(await _load(exchange_id), user)
    participant = next((item for item in updated.participants if item.user_id == user["id"]), None)
    if participant is None:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You are not in this exchange")
    return FulfilmentResponse(participant=participant, exchange_status=updated.status)


@router.post("/{exchange_id}/complete", response_model=ExchangeDetail)
async def complete(exchange_id: str, user: dict = Depends(get_current_user)):
    await svc.complete(await _load(exchange_id), user)
    log_event(logger, "exchange.complete_requested", exchange_id=exchange_id, user_id=user["id"])
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/dispute", response_model=ExchangeDetail)
async def dispute(exchange_id: str, payload: DisputeRequest, user: dict = Depends(get_current_user)):
    await svc.open_dispute(await _load(exchange_id), user, payload.reason.strip())
    return await _detail(exchange_id, user)


@router.post("/{exchange_id}/dispute/resolve", response_model=ExchangeDetail)
async def resolve(exchange_id: str, payload: ReasonRequest | None = None, user: dict = Depends(get_current_user)):
    await svc.resolve_dispute(await _load(exchange_id), user, (payload.reason if payload else "").strip())
    return await _detail(exchange_id, user)

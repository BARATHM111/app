"""Admin: dispute oversight. Requires a user with role "admin" (seeded: admin@barterx.dev)."""

from fastapi import APIRouter, Depends, HTTPException, status as http_status

from lib.db import db
from lib.deps import get_admin_user
from models.exchanges import AdminResolveRequest, ExchangeBrief, ExchangeDetail, ExchangeListResponse
from services import exchanges as svc

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.get("/disputes", response_model=ExchangeListResponse)
async def list_disputes(admin: dict = Depends(get_admin_user)):
    docs = await db.exchanges.find({"status": "disputed"}).sort([("updated_at", -1)]).to_list(200)
    briefs: list[ExchangeBrief] = [await svc.serialize_brief(doc, None) for doc in docs]
    return ExchangeListResponse(exchanges=briefs)


@router.post("/exchanges/{exchange_id}/resolve", response_model=ExchangeDetail)
async def resolve(exchange_id: str, payload: AdminResolveRequest, admin: dict = Depends(get_admin_user)):
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
    await svc.admin_resolve(exchange, admin, payload.action, payload.note.strip())
    history = await svc.exchange_history(exchange_id)
    return ExchangeDetail(exchange=await svc.serialize_exchange(await db.exchanges.find_one({"id": exchange_id}), admin["id"]), **history)

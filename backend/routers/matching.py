"""MatchingModule + GraphEngineModule — semantic candidates and deterministic cycles."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from lib.db import db
from lib.dates import utc_now
from lib.deps import get_current_user
from lib.log import log_event
from models.ai import GraphStats
from models.common import MessageResponse
from models.matches import MatchPage
from models.wants import CycleListResponse
from services import graph as graph_service
from services.matching import compute_matches_for_user

router = APIRouter(prefix="/v1", tags=["matching"])
logger = logging.getLogger("barterx.matching")


@router.get("/matches", response_model=MatchPage)
async def list_matches(user: dict = Depends(get_current_user)):
    matches = await compute_matches_for_user(user["id"])
    log_event(logger, "matches.computed", user_id=user["id"], count=len(matches))
    return MatchPage(items=matches, total=len(matches), page=1, page_size=max(1, len(matches)), pages=1)


@router.post("/matches/{match_id}/dismiss", response_model=MessageResponse)
async def dismiss_match(match_id: str, user: dict = Depends(get_current_user)):
    match = await db.matches.find_one({"id": match_id})
    if not match:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Match not found")
    if match["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="This match is not yours")
    await db.matches.update_one({"id": match_id}, {"$set": {"dismissed": True}})
    return MessageResponse(message="Match dismissed")


@router.get("/cycles", response_model=CycleListResponse)
async def list_cycles(
    max_nodes: int = Query(default=3, ge=2, le=3),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Public read: cycles only expose marketplace-public data. Proposing one requires auth."""
    cycles = await graph_service.discover_cycles(max_nodes=max_nodes, limit=limit)
    return CycleListResponse(cycles=cycles, candidate_count=len(cycles), generated_at=utc_now())


@router.get("/graph/stats", response_model=GraphStats)
async def graph_stats():
    stats = await graph_service.graph_stats()
    return GraphStats(
        nodes=stats["nodes"],
        edges=stats["edges"],
        two_cycles=stats["two_cycles"],
        three_cycles=stats["three_cycles"],
        generated_at=stats["generated_at"],
        note=stats.get("note"),
    )

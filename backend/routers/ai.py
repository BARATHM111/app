"""AIModule: listing intelligence, explanations, deal summaries and embeddings.

Every endpoint here is advisory. Nothing in this module can approve a proposal,
authorise a payment or change an exchange's state. A provider failure is returned
as an error (503 not configured, 504 timeout, 502 failed or invalid output) and
is never replaced with invented content.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.deps import get_current_user
from lib.embeddings import EmbeddingError, get_embedding_provider
from lib.log import log_event
from models.ai import (
    AIStatus,
    AnalyzeListingRequest,
    AnalyzeListingResponse,
    CategorizeRequest,
    CategorizeResponse,
    DealSummaryRequest,
    DealSummaryResponse,
    EmbeddingStatus,
    ExtractListingRequest,
    ExtractListingResponse,
    GraphStats,
    ReembedRequest,
    ReembedResponse,
    SimilarListing,
    SimilarListingsResponse,
)
from models.matches import MatchExplanationRequest, MatchExplanationResponse
from services import ai
from services import embeddings as embedding_service
from services import graph as graph_service
from services.exchanges import exchange_history, get_participant_or_403, serialize_exchange

router = APIRouter(prefix="/v1/ai", tags=["ai"])
logger = logging.getLogger("barterx.ai")


def _ai_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ai.AIUnavailable):
        return HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, ai.AITimeout):
        return HTTPException(status_code=http_status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc))
    return HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=f"AI request failed: {exc}")


@router.get("/status", response_model=AIStatus)
async def ai_status():
    available = ai.is_available()
    provider = get_embedding_provider()
    return AIStatus(
        available=available,
        model=ai.model_label(),
        embeddings_model=f"{provider.model}@v{provider.version}",
        embeddings_provider=provider.name,
        detail=(
            "LLM and embeddings are ready."
            if available
            else "The LLM key is missing on the backend. AI endpoints are disabled, but matching and "
            "cycles still work with the deterministic engine."
        ),
    )


@router.post("/analyze-listing", response_model=AnalyzeListingResponse)
async def analyze_listing(payload: AnalyzeListingRequest, user: dict = Depends(get_current_user)):
    try:
        analysis = await ai.analyze_listing(payload.text)
    except (ai.AIUnavailable, ai.AIError) as exc:
        log_event(logger, "ai.analyze_failed", user_id=user["id"], error=str(exc)[:300])
        raise _ai_error(exc) from exc
    log_event(logger, "ai.analyze", user_id=user["id"], category=analysis.category, value_basis=analysis.value_basis)
    return AnalyzeListingResponse(analysis=analysis, model=ai.model_label(), generated_at=utc_now())


@router.post("/extract-listing", response_model=ExtractListingResponse)
async def extract_listing(payload: ExtractListingRequest, user: dict = Depends(get_current_user)):
    """Older endpoint kept for compatibility. It runs the same validated analysis pipeline."""
    try:
        extraction = await ai.extract_listing(payload.text)
    except (ai.AIUnavailable, ai.AIError) as exc:
        raise _ai_error(exc) from exc
    return ExtractListingResponse(extraction=extraction, model=ai.model_label(), generated_at=utc_now())


@router.post("/categorize", response_model=CategorizeResponse)
async def categorize(payload: CategorizeRequest, user: dict = Depends(get_current_user)):
    try:
        categories = await ai.categorize(payload.text)
    except (ai.AIUnavailable, ai.AIError) as exc:
        raise _ai_error(exc) from exc
    return CategorizeResponse(categories=categories, primary=categories[0], model=ai.model_label(), generated_at=utc_now())


async def _explain(payload: MatchExplanationRequest, user: dict) -> MatchExplanationResponse:
    match = await db.matches.find_one({"id": payload.match_id})
    if not match:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Match not found")
    if match["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="This match is not yours")

    if match.get("explanation"):
        return MatchExplanationResponse(
            match_id=match["id"],
            explanation=match["explanation"],
            model=match.get("explanation_model") or ai.model_label(),
            generated_at=clean_doc({"created_at": match["explanation_generated_at"]})["created_at"],
            cached=True,
        )

    from services.matching import match_context  # local import avoids a module cycle

    context = await match_context(match["id"])
    try:
        explanation = await ai.match_explanation(context or {})
    except (ai.AIUnavailable, ai.AIError) as exc:
        raise _ai_error(exc) from exc

    now = utc_now()
    await db.matches.update_one(
        {"id": match["id"]},
        {"$set": {"explanation": explanation, "explanation_generated_at": now, "explanation_model": ai.model_label()}},
    )
    return MatchExplanationResponse(match_id=match["id"], explanation=explanation, model=ai.model_label(), generated_at=now)


@router.post("/explain-match", response_model=MatchExplanationResponse)
async def explain_match(payload: MatchExplanationRequest, user: dict = Depends(get_current_user)):
    return await _explain(payload, user)


@router.post("/match-explanation", response_model=MatchExplanationResponse, include_in_schema=False)
async def match_explanation_alias(payload: MatchExplanationRequest, user: dict = Depends(get_current_user)):
    return await _explain(payload, user)


@router.post("/deal-summary", response_model=DealSummaryResponse)
async def deal_summary(payload: DealSummaryRequest, user: dict = Depends(get_current_user)):
    exchange = await db.exchanges.find_one({"id": payload.exchange_id})
    if not exchange:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exchange not found")
    await get_participant_or_403(exchange["id"], user)

    history = await exchange_history(exchange["id"])
    serialised = await serialize_exchange(exchange, user["id"])
    context = {
        "exchange_id": exchange["id"],
        "status": exchange["status"],
        "revision": exchange.get("revision", 1),
        "participants": [
            {
                "name": participant.user.name if participant.user else participant.user_id,
                "gives": participant.gives_listing.title if participant.gives_listing else None,
                "gives_value": participant.value_given,
                "receives": participant.receives_listing.title if participant.receives_listing else None,
                "receives_value": participant.value_received,
                "balance_amount": participant.balance_amount,
                "approval_status": participant.approval_status.value,
                "fulfilment_status": participant.fulfilment_status.value,
            }
            for participant in serialised.participants
        ],
        "currency": serialised.currency,
        "payment_summary": serialised.payment_summary.model_dump(),
        "open_offers": [offer.message for offer in history["offers"] if offer.status.value == "open"],
    }
    try:
        summary = await ai.deal_summary(context)
    except (ai.AIUnavailable, ai.AIError) as exc:
        raise _ai_error(exc) from exc
    return DealSummaryResponse(
        exchange_id=exchange["id"],
        summary=summary["summary"],
        open_questions=summary["open_questions"],
        negotiation_suggestions=summary["negotiation_suggestions"],
        model=ai.model_label(),
        generated_at=utc_now(),
    )


# ------------------------------------------------------------------ embeddings


@router.get("/embeddings/status", response_model=EmbeddingStatus)
async def embeddings_status():
    return EmbeddingStatus(**(await embedding_service.embedding_status()))


@router.post("/embeddings/reembed", response_model=ReembedResponse)
async def reembed(payload: ReembedRequest | None = None, user: dict = Depends(get_current_user)):
    """Re-embed listings and wants whose vectors are missing, stale or out of date (or all of them, with force)."""
    result = await embedding_service.reembed_all(force=bool(payload and payload.force))
    log_event(logger, "ai.reembed", user_id=user["id"], **result)
    return ReembedResponse(**result, status=EmbeddingStatus(**(await embedding_service.embedding_status())))


@router.post("/rebuild-embeddings", response_model=ReembedResponse, include_in_schema=False)
async def rebuild_embeddings_alias(user: dict = Depends(get_current_user)):
    result = await embedding_service.reembed_all(force=True)
    return ReembedResponse(**result, status=EmbeddingStatus(**(await embedding_service.embedding_status())))


@router.get("/similar-listings", response_model=SimilarListingsResponse)
async def similar_listings(
    want_id: str = Query(..., min_length=1),
    limit: int = Query(default=10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """Cosine nearest-neighbour listings for one of your wants (similarity only, no compatibility rules)."""
    want = await db.wants.find_one({"id": want_id})
    if not want:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Want not found")
    if want["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="This want is not yours")
    try:
        neighbours = await embedding_service.similar_listings_for_want(want, limit)
    except EmbeddingError as exc:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    listings = {
        doc["id"]: doc
        for doc in await db.listings.find({"id": {"$in": [n.subject_id for n in neighbours]}}).to_list(len(neighbours))
    }
    provider = get_embedding_provider()
    items = [
        SimilarListing(
            listing_id=n.subject_id,
            title=listings[n.subject_id]["title"],
            category=listings[n.subject_id].get("category", "Other"),
            type=listings[n.subject_id]["type"],
            estimated_value=float(listings[n.subject_id]["estimated_value"]),
            currency=listings[n.subject_id].get("currency", "USD"),
            owner_id=n.owner_id,
            score=n.score,
        )
        for n in neighbours
        if n.subject_id in listings and listings[n.subject_id].get("status") == "active"
    ]
    return SimilarListingsResponse(want_id=want_id, model=provider.model, version=provider.version, items=items)


@router.get("/graph-stats", response_model=GraphStats)
async def ai_graph_stats():
    stats = await graph_service.graph_stats()
    return GraphStats(
        nodes=stats["nodes"],
        edges=stats["edges"],
        two_cycles=stats["two_cycles"],
        three_cycles=stats["three_cycles"],
        generated_at=stats["generated_at"],
        note=stats.get("note"),
    )

"""Semantic matching: embeddings propose candidates, deterministic rules validate them."""

from datetime import datetime
from typing import Any, Dict, List

from lib.db import db
from lib.dates import clean_doc, utc_now
from models.listings import ListingBrief
from models.matches import Match
from services.embeddings import pair_scores
from services.compatibility import round_money
from services.reservations import reserved_listing_ids
from services.scoring import ScoringConfig, score_pair

MAX_CANDIDATES_PER_WANT = 40


async def _locked_listing_ids() -> set[str]:
    """Listings held by an active exchange (the reservation ledger). Never offered twice."""
    return await reserved_listing_ids()


async def _open_wants_with_offer(user_id: str) -> List[Dict[str, Any]]:
    wants = await db.wants.find({"user_id": user_id, "status": "open"}).to_list(200)
    for want in wants:
        want = clean_doc(want)
        if want.get("listing_id"):
            listing = await db.listings.find_one({"id": want["listing_id"]})
            if listing:
                want["offered_value"] = listing.get("estimated_value")
                want["offered_listing"] = listing
    return wants


async def compute_matches_for_user(user_id: str) -> List[Match]:
    """Build/replace the semantic candidate set for one trader's open wants."""
    wants = await _open_wants_with_offer(user_id)
    if not wants:
        return []

    locked = await _locked_listing_ids()
    matches: List[Match] = []

    for want in wants:
        candidates = await db.listings.find(
            {
                "status": "active",
                "owner_id": {"$ne": user_id},
                "currency": want["currency"],
            }
        ).to_list(500)

        owner = await db.users.find_one({"id": user_id}, {"location": 1}) or {}
        config = ScoringConfig.from_env()
        available = [listing for listing in candidates if listing["id"] not in locked]
        # Stored vectors (current model+version). A missing pair means the provider failed.
        scores = await pair_scores(available, [want])

        scored: List[tuple[float, dict, dict]] = []
        for listing in available:
            semantic = scores.get((listing["id"], want["id"]))
            result = score_pair(
                listing, want, semantic, want_location=owner.get("location", ""), reserved=frozenset(locked), config=config
            )
            if not result.ok:
                continue
            scored.append((result.score, listing, {"components": result.components, "semantic": result.components["semantic"], "value": result.components["value"], "strengths": result.reasons}))

        scored.sort(key=lambda row: (-row[0], -row[2]["semantic"], row[1]["id"]))
        for score, listing, meta in scored[:MAX_CANDIDATES_PER_WANT]:
            reasons = list(meta["strengths"])
            reasons.append("A score ranks recommendations. It does not prove an exchange is fair or feasible.")
            if want.get("offered_listing"):
                reasons.append(
                    f"Balances against your {want['offered_listing']['title']} "
                    f"({round_money(want['offered_listing']['estimated_value'])} "
                    f"{want['offered_listing']['currency']})"
                )
            match_id = f"{want['id']}__{listing['id']}"
            existing = await db.matches.find_one({"id": match_id})
            doc = {
                "id": match_id,
                "user_id": user_id,
                "want_id": want["id"],
                "candidate_listing_id": listing["id"],
                "score": score,
                "semantic_score": meta["semantic"],
                "value_score": meta["value"],
                "category_score": meta["components"]["category"],
                "location_score": meta["components"]["location"],
                "compatible": True,
                "reasons": reasons,
                "dismissed": bool(existing and existing.get("dismissed")),
                # An explanation is generated on request and cached, never invented here.
                "explanation": existing.get("explanation") if existing else None,
                "explanation_generated_at": existing.get("explanation_generated_at") if existing else None,
                "created_at": existing.get("created_at") if existing else utc_now(),
            }
            if doc["dismissed"]:
                continue
            await db.matches.update_one({"id": match_id}, {"$set": doc}, upsert=True)
            matches.append(_to_match(doc, listing, want.get("offered_listing")))

    matches.sort(key=lambda m: (-m.score, m.candidate_listing_id))
    return matches


def _to_match(doc: dict, listing: dict | None, offered: dict | None) -> Match:
    payload = clean_doc(dict(doc))
    payload["candidate_listing"] = (
        ListingBrief(
            id=listing["id"],
            title=listing["title"],
            type=listing["type"],
            category=listing.get("category", "Other"),
            estimated_value=listing["estimated_value"],
            currency=listing.get("currency", "USD"),
        )
        if listing
        else None
    )
    payload["offered_listing"] = (
        ListingBrief(
            id=offered["id"],
            title=offered["title"],
            type=offered["type"],
            category=offered.get("category", "Other"),
            estimated_value=offered["estimated_value"],
            currency=offered.get("currency", "USD"),
        )
        if offered
        else None
    )
    return Match(**payload)


async def match_context(match_id: str) -> Dict[str, Any] | None:
    """Everything the AI needs to explain a single match — and nothing more."""
    doc = await db.matches.find_one({"id": match_id})
    if not doc:
        return None
    want = await db.wants.find_one({"id": doc["want_id"]})
    listing = await db.listings.find_one({"id": doc["candidate_listing_id"]})
    owner = await db.users.find_one({"id": listing["owner_id"]}) if listing else None
    offered = await db.listings.find_one({"id": want["listing_id"]}) if want and want.get("listing_id") else None
    return {
        "match": clean_doc(doc),
        "want": want,
        "listing": listing,
        "listing_owner": owner,
        "offered_listing": offered,
    }


async def build_graph_snapshot() -> Dict[str, Any]:
    """Nodes/edges summary of the current trade graph (used by the graph stats endpoint)."""
    from services.graph import discover_cycles

    nodes = await db.listings.distinct("owner_id", {"status": "active"})
    cycles = await discover_cycles()
    edges = sum(len(cycle.edges) for cycle in cycles)
    return {"nodes": len(nodes), "edges": edges, "cycles": cycles}

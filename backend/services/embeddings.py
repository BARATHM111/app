"""Embedding service: turns listings and wants into stored vectors and scores pairs.

Failure policy: an embedding failure never blocks a listing/want write or a match feed.
It is logged (`embedding.failed`), the subject keeps no current vector, and its
semantic score is treated as 0 with the reason recorded; `reembed` retries later.
"""

import logging
from typing import Dict, Iterable, List, Tuple

from lib.db import db
from lib.embeddings import (
    EmbeddingError,
    cosine_similarity,
    get_embedding_provider,
    listing_text,
    source_hash,
    want_text,
)
from lib.log import log_event
from services.embedding_store import EmbeddingRecord, get_embedding_store

logger = logging.getLogger("barterx.embeddings")
BATCH_SIZE = 64


def subject_text(kind: str, doc: dict) -> str:
    if kind == "listing":
        return listing_text(doc.get("title", ""), doc.get("description", ""), doc.get("category", ""), doc.get("tags"))
    return want_text(doc.get("title", ""), doc.get("description", ""), doc.get("category", ""), doc.get("keywords"))


def _owner(kind: str, doc: dict) -> str:
    return doc.get("owner_id", "") if kind == "listing" else doc.get("user_id", "")


async def embed_subjects(kind: str, docs: List[dict], *, force: bool = False) -> Dict[str, List[float]]:
    """Ensure each doc has a current vector; returns {id: vector} for those that succeeded."""
    if not docs:
        return {}
    provider = get_embedding_provider()
    store = get_embedding_store()
    existing = await store.get_many(kind, [doc["id"] for doc in docs], provider.model, provider.version)

    vectors: Dict[str, List[float]] = {}
    pending: List[Tuple[dict, str, str]] = []
    for doc in docs:
        text = subject_text(kind, doc)
        digest = source_hash(text)
        record = existing.get(doc["id"])
        if record and record.source_hash == digest and not force:
            vectors[doc["id"]] = record.vector
        else:
            pending.append((doc, text, digest))

    for start in range(0, len(pending), BATCH_SIZE):
        batch = pending[start : start + BATCH_SIZE]
        try:
            embedded = await provider.embed([text for _, text, _ in batch])
        except EmbeddingError as exc:
            log_event(logger, "embedding.failed", kind=kind, count=len(batch), provider=provider.name, error=str(exc)[:300])
            continue
        for (doc, _, digest), vector in zip(batch, embedded):
            await store.upsert(
                EmbeddingRecord(
                    subject_kind=kind,
                    subject_id=doc["id"],
                    owner_id=_owner(kind, doc),
                    provider=provider.name,
                    model=provider.model,
                    version=provider.version,
                    dim=len(vector),
                    source_hash=digest,
                    vector=vector,
                )
            )
            vectors[doc["id"]] = vector
    return vectors


async def embed_listing(listing: dict) -> bool:
    return listing["id"] in await embed_subjects("listing", [listing])


async def embed_want(want: dict) -> bool:
    return want["id"] in await embed_subjects("want", [want])


async def delete_embedding(kind: str, subject_id: str) -> None:
    await get_embedding_store().delete(kind, subject_id)


async def pair_scores(listings: Iterable[dict], wants: Iterable[dict]) -> Dict[Tuple[str, str], float]:
    """Cosine score for every (listing_id, want_id) pair, from stored/current vectors.

    Pairs where either side has no vector (provider failure) are simply absent; callers
    treat absence as 0.0.
    """
    listings = list(listings)
    wants = list(wants)
    listing_vectors = await embed_subjects("listing", listings)
    want_vectors = await embed_subjects("want", wants)
    scores: Dict[Tuple[str, str], float] = {}
    for want in wants:
        want_vector = want_vectors.get(want["id"])
        if want_vector is None:
            continue
        for listing in listings:
            listing_vector = listing_vectors.get(listing["id"])
            if listing_vector is not None:
                scores[(listing["id"], want["id"])] = round(cosine_similarity(listing_vector, want_vector), 4)
    return scores


async def similar_listings_for_want(want: dict, limit: int = 10):
    """Cosine nearest-neighbour retrieval of listings for one want (excludes own listings)."""
    provider = get_embedding_provider()
    vectors = await embed_subjects("want", [want])
    vector = vectors.get(want["id"])
    if vector is None:
        raise EmbeddingError("Could not embed this want right now — try again shortly")
    # Make sure active listings have current vectors before searching.
    active = await db.listings.find({"status": "active", "owner_id": {"$ne": want["user_id"]}}).to_list(2000)
    await embed_subjects("listing", active)
    return await get_embedding_store().nearest(
        "listing", vector, provider.model, provider.version, limit, exclude_owner=want["user_id"]
    )


async def reembed_all(*, force: bool = False) -> Dict[str, int]:
    """Re-embed every listing and want whose vector is missing, stale (model/version) or outdated text."""
    provider = get_embedding_provider()
    store = get_embedding_store()
    result = {"listings": 0, "wants": 0, "failed": 0}
    for kind, collection, key in (("listing", db.listings, "listings"), ("want", db.wants, "wants")):
        docs = await collection.find({"status": {"$nin": ["archived", "closed"]}}).to_list(5000)
        hashes = await store.current_hashes(kind, provider.model, provider.version)
        todo = [d for d in docs if force or hashes.get(d["id"]) != source_hash(subject_text(kind, d))]
        done = await embed_subjects(kind, todo, force=force)
        result[key] = len(done)
        result["failed"] += len(todo) - len(done)
    log_event(logger, "embedding.reembedded", provider=provider.name, model=provider.model, version=provider.version, **result)
    return result


async def embedding_status() -> dict:
    provider = get_embedding_provider()
    store = get_embedding_store()
    return {**provider.describe(), "store": store.name, **(await store.counts(provider.model, provider.version))}

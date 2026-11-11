"""Listing reservations: one listing can be held by at most one active exchange.

`listing_reservations` has a unique index on listing_id, so claiming a listing is a
single atomic insert. Two exchanges racing for the same listing cannot both win: the
second insert raises DuplicateKeyError and that exchange rolls back its own claims.

When the MongoDB deployment supports multi-document transactions (a replica set or
Atlas), `atomic()` also runs the whole availability check, reservation and exchange
creation inside one transaction. On the in-pod standalone mongod that is not available,
so the unique index is the guarantee. The Postgres target does the same with
`SELECT ... FOR UPDATE` inside prisma.$transaction (see docs/08).
"""

import logging
from typing import Awaitable, Callable, Iterable, Optional, TypeVar

from fastapi import HTTPException, status as http_status
from pymongo.errors import DuplicateKeyError, OperationFailure

from lib.dates import utc_now
from lib.db import client, db
from lib.log import log_event

logger = logging.getLogger("barterx.reservations")
T = TypeVar("T")
_supports_tx: Optional[bool] = None


async def transactions_supported() -> bool:
    global _supports_tx
    if _supports_tx is None:
        try:
            hello = await db.command("hello")
            _supports_tx = bool(hello.get("setName") or hello.get("msg") == "isdbgrid")
        except OperationFailure:
            _supports_tx = False
    return _supports_tx


async def atomic(work: Callable[[object | None], Awaitable[T]]) -> T:
    """Run `work(session)` inside a transaction when supported, else with session=None."""
    if not await transactions_supported():
        return await work(None)
    async with await client.start_session() as session:
        async with session.start_transaction():
            return await work(session)


async def reserved_listing_ids() -> set[str]:
    return {doc["listing_id"] for doc in await db.listing_reservations.find({}, {"listing_id": 1}).to_list(5000)}


async def reserve_listings(exchange_id: str, listing_ids: Iterable[str], session=None) -> None:
    """Claim every listing for `exchange_id`, or none of them."""
    claimed: list[str] = []
    try:
        for listing_id in sorted(set(listing_ids)):
            await db.listing_reservations.insert_one(
                {"listing_id": listing_id, "exchange_id": exchange_id, "created_at": utc_now()}, session=session
            )
            claimed.append(listing_id)
    except DuplicateKeyError:
        if claimed and session is None:  # inside a transaction the abort undoes these
            await db.listing_reservations.delete_many({"exchange_id": exchange_id, "listing_id": {"$in": claimed}})
        log_event(logger, "reservation.conflict", exchange_id=exchange_id)
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="One of these listings was just reserved by another exchange. A listing can never be reserved twice.",
        )


async def release_listings(exchange_id: str, *, new_status: str) -> None:
    """Free (or mark traded) every listing held by `exchange_id`."""
    held = await db.listing_reservations.find({"exchange_id": exchange_id}).to_list(20)
    ids = [doc["listing_id"] for doc in held]
    if ids:
        await db.listings.update_many(
            {"id": {"$in": ids}}, {"$set": {"status": new_status, "updated_at": utc_now()}}
        )
    await db.listing_reservations.delete_many({"exchange_id": exchange_id})

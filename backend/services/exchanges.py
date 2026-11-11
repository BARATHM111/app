"""Exchange lifecycle: proposal → approvals → payments → fulfilment → completion.

Every transition is deterministic, derived from stored state, authorised for the acting user,
and written to the `exchange_events` audit trail. The AI layer has no path into this module.

States: proposed, pending_approval, approved, payment_pending, ready_for_fulfillment,
        fulfillment_in_progress, completed | rejected, cancelled, disputed, expired.
        ("discovered" applies to cycle candidates only; they are not stored as exchanges.)

Rules enforced here:
- Each participant approves only for themselves, and only the *current* revision.
- Any change of terms (counteroffer) bumps the revision and resets every approval.
- Listings are reserved atomically (unique reservation ledger, plus a transaction when available).
- Completion is an explicit action, allowed only once every payment is verified and every
  participant has confirmed fulfilment. Payment and fulfilment are separate stages.
"""

import logging
import os
from datetime import timedelta
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import HTTPException, status as http_status
from pymongo import ASCENDING

from lib.dates import clean_doc, utc_now
from lib.db import db
from lib.log import log_event
from models.common import (
    ApprovalDecision,
    ApprovalStatus,
    ExchangeStatus,
    FulfilmentStatus,
    NotificationType,
    PaymentStatus,
)
from models.exchanges import (
    Exchange,
    ExchangeApproval,
    ExchangeBrief,
    ExchangeEvent,
    ExchangeParticipant,
    Offer,
    PaymentSummary,
)
from models.listings import ListingBrief
from models.users import UserBrief
from services.compatibility import ACTIVE_EXCHANGE_STATUSES, round_money
from services.notifications import notify_many
from services.reservations import atomic, release_listings, reserve_listings

logger = logging.getLogger("barterx.exchanges")

S = ExchangeStatus
HOLDING = set(ACTIVE_EXCHANGE_STATUSES)
TERMINAL_EXCHANGE_STATUSES = (S.completed.value, S.rejected.value, S.cancelled.value, S.expired.value)
NEGOTIABLE = (S.proposed.value, S.pending_approval.value, S.approved.value)
DISPUTABLE = (S.approved.value, S.payment_pending.value, S.ready_for_fulfillment.value, S.fulfillment_in_progress.value)
OPEN_PAYMENT_STATUSES = (PaymentStatus.created.value, PaymentStatus.approved.value, PaymentStatus.pending.value)


def expiry_days() -> float:
    try:
        return max(0.0, float(os.environ.get("PROPOSAL_EXPIRY_DAYS", "3")))
    except ValueError:
        return 3.0


def _expires_at(now):
    days = expiry_days()
    return now + timedelta(days=days) if days > 0 else None


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=detail)


# ------------------------------------------------------------------------------------------ reads

def _listing_brief(listing: dict | None) -> ListingBrief | None:
    if not listing:
        return None
    return ListingBrief(
        id=listing["id"],
        title=listing["title"],
        type=listing["type"],
        category=listing.get("category", "Other"),
        estimated_value=float(listing["estimated_value"]),
        currency=listing.get("currency", "USD"),
    )


def _user_brief(user: dict | None) -> UserBrief | None:
    if not user:
        return None
    return UserBrief(id=user["id"], name=user["name"], location=user.get("location", ""))


async def load_participants(exchange_id: str) -> List[dict]:
    return await db.exchange_participants.find({"exchange_id": exchange_id}).sort("created_at", ASCENDING).to_list(10)


async def _payments(exchange_id: str) -> List[dict]:
    return await db.payments.find({"exchange_id": exchange_id}).to_list(50)


def _verified_ids(payments: List[dict]) -> set:
    return {p["participant_id"] for p in payments if p.get("status") == PaymentStatus.captured.value and p.get("verified")}


async def payment_summary_for(exchange_id: str, participants: List[dict]) -> PaymentSummary:
    payments = await _payments(exchange_id)
    payers = [p for p in participants if round_money(p.get("balance_amount") or 0) > 0]
    verified = _verified_ids(payments)
    return PaymentSummary(
        required=len(payers),
        captured=len([p for p in payers if p["id"] in verified]),
        total_due=round_money(sum(round_money(p["balance_amount"]) for p in payers)),
        total_captured=round_money(sum(float(p.get("amount") or 0) for p in payments if p.get("verified"))),
        currency=participants[0].get("currency", "USD") if participants else "USD",
        all_verified=all(p["id"] in verified for p in payers),
    )


def _approved_current(exchange: dict, participants: List[dict]) -> List[dict]:
    revision = exchange.get("revision", 1)
    return [
        p for p in participants
        if p.get("approval_status") == ApprovalStatus.approved.value and p.get("approved_revision") == revision
    ]


def allowed_actions(exchange: dict, participants: List[dict], payments: List[dict], viewer_id: Optional[str]) -> List[str]:
    """What this viewer may do right now. The UI renders these; the server re-checks every one."""
    me = next((p for p in participants if p["user_id"] == viewer_id), None)
    if not me:
        return []
    status = exchange["status"]
    verified_any = bool(_verified_ids(payments))
    actions: List[str] = []
    if status in (S.proposed.value, S.pending_approval.value):
        if not (me.get("approval_status") == ApprovalStatus.approved.value and me.get("approved_revision") == exchange.get("revision", 1)):
            actions.append("approve")
    if status in NEGOTIABLE + (S.payment_pending.value,) and not verified_any:
        actions += ["counteroffer", "reject"]
    if status in HOLDING and status != S.disputed.value and not verified_any:
        actions.append("cancel")
    if status in (S.approved.value, S.payment_pending.value) and round_money(me.get("balance_amount") or 0) > 0 and me["id"] not in _verified_ids(payments):
        actions.append("pay")
    if status in (S.ready_for_fulfillment.value, S.fulfillment_in_progress.value) and me.get("fulfilment_status") != FulfilmentStatus.confirmed.value:
        actions.append("confirm_fulfilment")
    if status == S.fulfillment_in_progress.value and all(p.get("fulfilment_status") == FulfilmentStatus.confirmed.value for p in participants):
        actions.append("complete")
    if status in DISPUTABLE:
        actions.append("dispute")
    if status == S.disputed.value and viewer_id not in ((exchange.get("dispute") or {}).get("resolved_by") or []):
        actions.append("resolve_dispute")
    return actions


async def serialize_exchange(exchange: dict, viewer_id: str | None = None, *, with_children: bool = False) -> Exchange:
    participants = await load_participants(exchange["id"])
    payments = await _payments(exchange["id"])
    user_ids = [p["user_id"] for p in participants]
    listing_ids = list({p["gives_listing_id"] for p in participants} | {p["receives_listing_id"] for p in participants})
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": user_ids}}).to_list(10)} if user_ids else {}
    listings = {l["id"]: l for l in await db.listings.find({"id": {"$in": listing_ids}}).to_list(20)} if listing_ids else {}

    models: List[ExchangeParticipant] = []
    for participant in participants:
        doc = clean_doc(dict(participant))
        doc["user"] = _user_brief(users.get(participant["user_id"]))
        doc["gives_listing"] = _listing_brief(listings.get(participant["gives_listing_id"]))
        doc["receives_listing"] = _listing_brief(listings.get(participant["receives_listing_id"]))
        doc["fulfilled_at"] = clean_doc({"created_at": participant.get("fulfilled_at")})["created_at"]
        models.append(ExchangeParticipant(**doc))

    mine = next((p for p in models if p.user_id == viewer_id), None)
    payload = clean_doc(dict(exchange))
    for field in ("completed_at", "expires_at", "revised_at"):
        payload[field] = clean_doc({"created_at": exchange.get(field)})["created_at"]
    if exchange.get("dispute"):
        dispute = dict(exchange["dispute"])
        dispute["opened_at"] = clean_doc({"created_at": dispute.get("opened_at")})["created_at"]
        payload["dispute"] = dispute
    payload.update(
        participants=models,
        payment_summary=await payment_summary_for(exchange["id"], participants),
        approvals_current=len(_approved_current(exchange, participants)),
        approvals_required=len(participants),
        is_participant=mine is not None,
        my_participant=mine,
        allowed_actions=allowed_actions(exchange, participants, payments, viewer_id),
    )
    payload.setdefault("value_summary", {})
    return Exchange(**payload)


async def serialize_brief(exchange: dict, viewer_id: str | None = None) -> ExchangeBrief:
    participants = await load_participants(exchange["id"])
    others = [p["user_id"] for p in participants if p["user_id"] != viewer_id]
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": others}}).to_list(10)} if others else {}
    mine = next((p for p in participants if p["user_id"] == viewer_id), None)
    payload = clean_doc(dict(exchange))
    balance = round_money((mine or {}).get("balance_amount") or 0)
    return ExchangeBrief(
        id=exchange["id"],
        cycle_type=exchange.get("cycle_type", 2),
        status=exchange["status"],
        revision=exchange.get("revision", 1),
        currency=exchange.get("currency", "USD"),
        my_role=("payer" if balance > 0 else "receiver" if mine else None),
        my_balance=balance if mine else None,
        counterparties=[_user_brief(users[uid]) for uid in others if uid in users],
        total_value=round_money(sum(float(p.get("value_given") or 0) for p in participants)),
        created_at=payload["created_at"],
        updated_at=payload["updated_at"],
    )


# ------------------------------------------------------------------------------ state machine core

async def _event(exchange_id: str, actor_id: Optional[str], kind: str, from_status: str, to_status: str, note: str = "", revision: int = 1) -> None:
    await db.exchange_events.insert_one(
        {
            "id": f"ev_{uuid4().hex[:12]}",
            "exchange_id": exchange_id,
            "actor_id": actor_id,
            "kind": kind,
            "from_status": from_status,
            "to_status": to_status,
            "revision": revision,
            "note": note[:1000],
            "created_at": utc_now(),
        }
    )
    log_event(logger, f"exchange.{kind}", exchange_id=exchange_id, actor=actor_id, from_status=from_status, to_status=to_status, revision=revision)


def derive_status(exchange: dict, participants: List[dict], payments: List[dict]) -> str:
    """Pure: the non-terminal status implied by approvals, payments and fulfilment."""
    status = exchange["status"]
    if status in TERMINAL_EXCHANGE_STATUSES or status == S.disputed.value:
        return status
    approved = len(_approved_current(exchange, participants))
    if approved == 0:
        return S.proposed.value
    if approved < len(participants):
        return S.pending_approval.value
    payers = [p for p in participants if round_money(p.get("balance_amount") or 0) > 0]
    verified = _verified_ids(payments)
    if payers and not all(p["id"] in verified for p in payers):
        revision = exchange.get("revision", 1)
        started = any(p.get("status") in OPEN_PAYMENT_STATUSES + (PaymentStatus.captured.value,) and p.get("revision", revision) == revision for p in payments)
        return S.payment_pending.value if started else S.approved.value
    confirmed = [p for p in participants if p.get("fulfilment_status") == FulfilmentStatus.confirmed.value]
    return S.fulfillment_in_progress.value if confirmed else S.ready_for_fulfillment.value


async def _set_status(exchange: dict, new_status: str, actor_id: Optional[str], kind: str, note: str = "", extra: Optional[dict] = None) -> dict:
    old = exchange["status"]
    updates = {"status": new_status, "updated_at": utc_now(), **(extra or {})}
    await db.exchanges.update_one({"id": exchange["id"]}, {"$set": updates})
    if old != new_status or kind != "status_changed":
        await _event(exchange["id"], actor_id, kind, old, new_status, note, exchange.get("revision", 1))
    return {**exchange, **updates}


async def _close(exchange: dict, new_status: str, actor_id: Optional[str], kind: str, note: str = "") -> dict:
    """Terminal transition: release reservations and drop unverified payment orders."""
    listing_status = "traded" if new_status == S.completed.value else "active"
    await release_listings(exchange["id"], new_status=listing_status)
    if new_status != S.completed.value:
        await db.payments.update_many(
            {"exchange_id": exchange["id"], "status": {"$in": list(OPEN_PAYMENT_STATUSES)}},
            {"$set": {"status": PaymentStatus.cancelled.value, "last_error": f"Exchange {new_status}", "updated_at": utc_now()}},
        )
    extra = {"completed_at": utc_now()} if new_status == S.completed.value else {}
    return await _set_status(exchange, new_status, actor_id, kind, note, extra)


async def expire_if_due(exchange: dict) -> dict:
    expires_at = exchange.get("expires_at")
    if exchange["status"] in (S.proposed.value, S.pending_approval.value) and expires_at:
        if clean_doc({"created_at": expires_at})["created_at"] <= utc_now():
            exchange = await _close(exchange, S.expired.value, None, "expired", f"No full approval within {expiry_days():g} days")
            await notify_many(exchange["participant_ids"], NotificationType.exchange, "Exchange proposal expired",
                              "Not everyone approved in time, so the listings are back on the market.", f"/proposal/{exchange['id']}")
    return exchange


async def refresh_exchange_state(exchange_id: str, viewer_id: str | None = None, *, with_children: bool = False):
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange:
        return None
    exchange = await expire_if_due(exchange)
    new_status = derive_status(exchange, await load_participants(exchange_id), await _payments(exchange_id))
    if new_status != exchange["status"]:
        exchange = await _set_status(exchange, new_status, None, "status_changed")
    if with_children:
        return exchange
    return await serialize_exchange(exchange, viewer_id)


# -------------------------------------------------------------------------------------- actions

async def get_participant_or_403(exchange_id: str, user: dict) -> dict:
    """Authorisation gate: the *session user* must be a participant. No acting on behalf of others."""
    participant = await db.exchange_participants.find_one({"exchange_id": exchange_id, "user_id": user["id"]})
    if not participant:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Only a participant of this exchange can do that")
    return participant


async def create_exchange_from_cycle(cycle, user: dict) -> str:
    """Turn a re-derived cycle into a proposal (status proposed, never approved). Values come from the server."""
    if user["id"] not in cycle.participant_ids:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You are not part of this cycle")
    if len({p.currency for p in cycle.participants}) != 1:
        raise _conflict("All participants in an exchange must trade in the same currency")
    if await db.exchanges.find_one({"cycle_key": cycle.key, "status": {"$in": list(HOLDING)}}):
        raise _conflict("A proposal for this cycle is already in progress")

    exchange_id = f"ex_{uuid4().hex[:12]}"
    now = utc_now()
    gives = [p.gives_listing_id for p in cycle.participants]

    async def work(session):
        # Availability check inside the same unit of work as the reservation.
        listings = await db.listings.find({"id": {"$in": gives}}, session=session).to_list(10)
        by_id = {l["id"]: l for l in listings}
        for participant in cycle.participants:
            listing = by_id.get(participant.gives_listing_id)
            if not listing or listing.get("status") != "active" or listing.get("owner_id") != participant.user_id:
                raise _conflict(f"Listing '{participant.gives_listing_title}' is no longer available from its owner")
        await reserve_listings(exchange_id, gives, session=session)
        try:
            await db.exchanges.insert_one(
                {
                    "id": exchange_id,
                    "cycle_key": cycle.key,
                    "cycle_type": cycle.cycle_type,
                    "status": S.proposed.value,
                    "revision": 1,
                    "revised_at": now,
                    "expires_at": _expires_at(now),
                    "participant_ids": list(cycle.participant_ids),
                    "currency": cycle.participants[0].currency,
                    "value_summary": {
                        "total_value": cycle.total_value,
                        "total_imbalance": cycle.total_imbalance,
                        "min_edge_score": cycle.min_edge_score,
                        "avg_edge_score": cycle.avg_edge_score,
                    },
                    "created_by": user["id"],
                    "created_at": now,
                    "updated_at": now,
                    "completed_at": None,
                },
                session=session,
            )
            await db.exchange_participants.insert_many(
                [
                    {
                        "id": f"pp_{exchange_id}_{p.user_id}",
                        "exchange_id": exchange_id,
                        "user_id": p.user_id,
                        "gives_listing_id": p.gives_listing_id,
                        "receives_listing_id": p.receives_listing_id,
                        "listing_value_given": p.gives_value,
                        "value_given": p.gives_value,
                        "value_received": p.receives_value,
                        "balance_amount": p.balance_amount,
                        "currency": p.currency,
                        "receives_via_want_id": p.receives_via_want_id,
                        "approval_status": ApprovalStatus.pending.value,
                        "approved_revision": None,
                        "changes_note": None,
                        "fulfilment_status": FulfilmentStatus.pending.value,
                        "fulfilled_at": None,
                        "created_at": now,
                    }
                    for p in cycle.participants
                ],
                session=session,
            )
            await db.listings.update_many({"id": {"$in": gives}}, {"$set": {"status": "reserved", "updated_at": now}}, session=session)
        except Exception:
            if session is None:  # without a transaction, undo by hand
                await db.listing_reservations.delete_many({"exchange_id": exchange_id})
                await db.exchanges.delete_one({"id": exchange_id})
                await db.exchange_participants.delete_many({"exchange_id": exchange_id})
            raise

    await atomic(work)
    await _event(exchange_id, user["id"], "proposed", S.discovered.value, S.proposed.value, f"From cycle {cycle.key}")
    await notify_many([uid for uid in cycle.participant_ids if uid != user["id"]], NotificationType.cycle,
                      "New cycle proposal needs your approval",
                      f"A {cycle.cycle_type}-party exchange involving your listing is ready for review.", f"/proposal/{exchange_id}")
    return exchange_id


async def _record_approval_row(exchange: dict, participant: dict, user: dict, decision: str, note: str) -> None:
    now = utc_now()
    await db.exchange_approvals.insert_one(
        {
            "id": f"ap_{uuid4().hex[:12]}",
            "exchange_id": exchange["id"],
            "participant_id": participant["id"],
            "user_id": user["id"],
            "revision": exchange.get("revision", 1),
            "decision": decision,
            "note": note,
            "created_at": now,
        }
    )


async def approve(exchange: dict, user: dict, revision: Optional[int], note: str = "") -> Exchange:
    exchange = await expire_if_due(exchange)
    participant = await get_participant_or_403(exchange["id"], user)
    current = exchange.get("revision", 1)
    if exchange["status"] not in (S.proposed.value, S.pending_approval.value):
        raise _conflict(f"This exchange cannot be approved while it is {exchange['status'].replace('_', ' ')}")
    if revision is not None and revision != current:
        raise _conflict(f"The terms changed. You reviewed revision {revision}, but the current one is {current}. Review it again before approving.")
    if participant.get("approval_status") == ApprovalStatus.approved.value and participant.get("approved_revision") == current:
        return await refresh_exchange_state(exchange["id"], user["id"])  # idempotent
    await _record_approval_row(exchange, participant, user, ApprovalDecision.approved.value, note)
    await db.exchange_participants.update_one(
        {"id": participant["id"]},
        {"$set": {"approval_status": ApprovalStatus.approved.value, "approved_revision": current, "changes_note": None}},
    )
    await _event(exchange["id"], user["id"], "approved", exchange["status"], exchange["status"], note, current)
    await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.approval,
                      f"{user['name']} approved revision {current}", note or "Every participant must approve the same revision.",
                      f"/proposal/{exchange['id']}")
    return await refresh_exchange_state(exchange["id"], user["id"])


async def record_decision(exchange: dict, user: dict, decision: ApprovalDecision, note: str = "", revision: Optional[int] = None) -> Exchange:
    """Back-compat entry point: approve, or request changes (which bumps the revision)."""
    if decision == ApprovalDecision.approved:
        return await approve(exchange, user, revision, note)
    return await _bump_revision(exchange, user, note or "Changes requested", None)


async def _bump_revision(exchange: dict, user: dict, message: str, new_values: Optional[Dict[str, float]]) -> Exchange:
    participant = await get_participant_or_403(exchange["id"], user)
    if exchange["status"] not in NEGOTIABLE + (S.payment_pending.value,):
        raise _conflict(f"Terms cannot change while the exchange is {exchange['status'].replace('_', ' ')}")
    payments = await _payments(exchange["id"])
    if _verified_ids(payments):
        raise _conflict("A balancing payment is already verified, so the terms are locked. Open a dispute instead.")

    participants = await load_participants(exchange["id"])
    previous = {p["gives_listing_id"]: round_money(p["value_given"]) for p in participants}
    terms = dict(previous)
    if new_values:
        unknown = set(new_values) - set(terms)
        if unknown:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Counteroffer references listings outside this exchange")
        terms.update({lid: round_money(v) for lid, v in new_values.items()})
        if terms == previous:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="The counteroffer does not change any value")

    current = exchange.get("revision", 1)
    new_revision = current + 1
    now = utc_now()
    await _record_approval_row(exchange, participant, user, ApprovalDecision.changes_requested.value, message)
    for p in participants:
        given = terms[p["gives_listing_id"]]
        received = terms[p["receives_listing_id"]]
        await db.exchange_participants.update_one(
            {"id": p["id"]},
            {"$set": {
                "value_given": given,
                "value_received": received,
                "balance_amount": round_money(received - given),
                "approval_status": ApprovalStatus.pending.value,
                "approved_revision": None,
                "changes_note": message if p["id"] == participant["id"] else p.get("changes_note"),
            }},
        )
    # Any PayPal order created for the old terms is void: the amounts may have changed.
    await db.payments.update_many(
        {"exchange_id": exchange["id"], "status": {"$in": list(OPEN_PAYMENT_STATUSES)}},
        {"$set": {"status": PaymentStatus.cancelled.value, "last_error": f"Terms changed to revision {new_revision}", "updated_at": now}},
    )
    if new_values:
        await db.offers.insert_one(
            {
                "id": f"of_{uuid4().hex[:12]}",
                "exchange_id": exchange["id"],
                "revision": new_revision,
                "from_user_id": user["id"],
                "from_user_name": user["name"],
                "to_user_id": "",
                "message": message,
                "proposed_changes": {"agreed_values": terms, "previous_values": previous},
                "status": "open",
                "created_at": now,
            }
        )
    await db.exchanges.update_one(
        {"id": exchange["id"]},
        {"$set": {"revision": new_revision, "revised_at": now, "expires_at": _expires_at(now), "status": S.proposed.value, "updated_at": now}},
    )
    kind = "counteroffer" if new_values else "changes_requested"
    await _event(exchange["id"], user["id"], kind, exchange["status"], S.proposed.value, message, new_revision)
    await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.approval,
                      f"{user['name']} {'sent a counteroffer' if new_values else 'requested changes'}",
                      f"{message} All approvals were reset. Review revision {new_revision}.", f"/proposal/{exchange['id']}")
    return await refresh_exchange_state(exchange["id"], user["id"])


async def counteroffer(exchange: dict, user: dict, agreed_values: Dict[str, float], message: str) -> Exchange:
    return await _bump_revision(exchange, user, message, agreed_values)


async def reject(exchange: dict, user: dict, reason: str = "") -> Exchange:
    """Ends this proposal for everyone. The rejector is removed from this cycle: it is never rediscovered."""
    await get_participant_or_403(exchange["id"], user)
    if exchange["status"] not in NEGOTIABLE + (S.payment_pending.value,):
        raise _conflict(f"A proposal that is {exchange['status'].replace('_', ' ')} cannot be rejected")
    if _verified_ids(await _payments(exchange["id"])):
        raise _conflict("A balancing payment is already verified. Open a dispute instead of rejecting.")
    await db.cycle_rejections.update_one(
        {"cycle_key": exchange.get("cycle_key", ""), "user_id": user["id"]},
        {"$setOnInsert": {"exchange_id": exchange["id"], "created_at": utc_now()}},
        upsert=True,
    )
    exchange = await _close(exchange, S.rejected.value, user["id"], "rejected", reason)
    await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.exchange,
                      f"{user['name']} rejected the proposal", reason or "Your listings are back on the market.",
                      f"/proposal/{exchange['id']}")
    return await serialize_exchange(exchange, user["id"])


async def cancel_exchange(exchange: dict, user: dict, reason: str = "") -> Exchange:
    await get_participant_or_403(exchange["id"], user)
    if exchange["status"] not in HOLDING or exchange["status"] == S.disputed.value:
        raise _conflict(f"An exchange that is {exchange['status'].replace('_', ' ')} cannot be cancelled")
    if _verified_ids(await _payments(exchange["id"])):
        raise _conflict("Money has already moved on this exchange. Open a dispute so it can be settled.")
    exchange = await _close(exchange, S.cancelled.value, user["id"], "cancelled", reason)
    await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.exchange,
                      f"{user['name']} cancelled the exchange", reason or "The proposal was withdrawn.", f"/proposal/{exchange['id']}")
    return await serialize_exchange(exchange, user["id"])


async def confirm_fulfilment(exchange: dict, user: dict) -> dict:
    participant = await get_participant_or_403(exchange["id"], user)
    if exchange["status"] not in (S.ready_for_fulfillment.value, S.fulfillment_in_progress.value):
        raise _conflict("Fulfilment can only be confirmed after every participant approved and every balancing payment is verified")
    if participant.get("fulfilment_status") != FulfilmentStatus.confirmed.value:
        await db.exchange_participants.update_one(
            {"id": participant["id"]}, {"$set": {"fulfilment_status": FulfilmentStatus.confirmed.value, "fulfilled_at": utc_now()}}
        )
        await _event(exchange["id"], user["id"], "fulfilment_confirmed", exchange["status"], exchange["status"], "", exchange.get("revision", 1))
        await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.fulfilment,
                          f"{user['name']} confirmed fulfilment", "Once everyone confirms, any participant can complete the exchange.",
                          f"/proposal/{exchange['id']}")
    return await refresh_exchange_state(exchange["id"], user["id"])


async def complete(exchange: dict, user: dict) -> Exchange:
    await get_participant_or_403(exchange["id"], user)
    participants = await load_participants(exchange["id"])
    if exchange["status"] != S.fulfillment_in_progress.value or not all(
        p.get("fulfilment_status") == FulfilmentStatus.confirmed.value for p in participants
    ):
        raise _conflict("Every participant must confirm fulfilment before the exchange can be completed")
    summary = await payment_summary_for(exchange["id"], participants)
    if not summary.all_verified:
        raise _conflict("Every balancing payment must be verified by PayPal before completion")
    exchange = await _close(exchange, S.completed.value, user["id"], "completed")
    await notify_many(exchange["participant_ids"], NotificationType.exchange, "Exchange completed",
                      "Thanks for trading. You can now leave a verified review.", f"/proposal/{exchange['id']}")
    from services.payouts import payout_completed_exchange  # local import: payouts imports payments

    await payout_completed_exchange(exchange["id"])  # automatic payouts; failures are recorded and claimable
    return await serialize_exchange(await db.exchanges.find_one({"id": exchange["id"]}), user["id"])


async def open_dispute(exchange: dict, user: dict, reason: str) -> Exchange:
    await get_participant_or_403(exchange["id"], user)
    if exchange["status"] not in DISPUTABLE:
        raise _conflict(f"An exchange that is {exchange['status'].replace('_', ' ')} cannot be disputed")
    dispute = {"opened_by": user["id"], "reason": reason, "opened_at": utc_now(), "resolved_by": [], "resolution": None}
    exchange = await _set_status(exchange, S.disputed.value, user["id"], "disputed", reason,
                                 {"dispute": dispute, "status_before_dispute": exchange["status"]})
    await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.exchange,
                      f"{user['name']} opened a dispute", reason, f"/proposal/{exchange['id']}")
    return await serialize_exchange(exchange, user["id"])


async def _resume_from_dispute(exchange: dict, actor_id: str, note: str) -> dict:
    resumed = {**exchange, "status": exchange.get("status_before_dispute") or S.approved.value}
    target = derive_status(resumed, await load_participants(exchange["id"]), await _payments(exchange["id"]))
    return await _set_status(exchange, target, actor_id, "dispute_resolved", note)


async def resolve_dispute(exchange: dict, user: dict, note: str = "") -> Exchange:
    """Each participant marks the dispute resolved. When all have, the exchange resumes."""
    await get_participant_or_403(exchange["id"], user)
    if exchange["status"] != S.disputed.value:
        raise _conflict("This exchange is not in dispute")
    await db.exchanges.update_one({"id": exchange["id"]}, {"$addToSet": {"dispute.resolved_by": user["id"]}})
    exchange = await db.exchanges.find_one({"id": exchange["id"]})
    resolved = set((exchange.get("dispute") or {}).get("resolved_by") or [])
    await _event(exchange["id"], user["id"], "dispute_resolution_vote", S.disputed.value, S.disputed.value, note, exchange.get("revision", 1))
    if resolved >= set(exchange["participant_ids"]):
        exchange = await _resume_from_dispute(exchange, user["id"], "All participants marked the dispute resolved")
        await notify_many(exchange["participant_ids"], NotificationType.exchange, "Dispute resolved", "The exchange has resumed.", f"/proposal/{exchange['id']}")
    return await serialize_exchange(exchange, user["id"])


async def admin_resolve(exchange: dict, admin: dict, action: str, note: str) -> Exchange:
    if exchange["status"] != S.disputed.value:
        raise _conflict("This exchange is not in dispute")
    await db.exchanges.update_one({"id": exchange["id"]}, {"$set": {"dispute.resolution": {"by": admin["id"], "action": action, "note": note}}})
    exchange = await db.exchanges.find_one({"id": exchange["id"]})
    if action == "resume":
        exchange = await _resume_from_dispute(exchange, admin["id"], f"Admin resumed: {note}")
    else:
        # Admin cancellation releases listings. Captured PayPal money is NOT refunded automatically:
        # refunds are handled manually in the PayPal dashboard (documented, never claimed as escrow).
        exchange = await _close(exchange, S.cancelled.value, admin["id"], "admin_cancelled", note)
    await notify_many(exchange["participant_ids"], NotificationType.exchange, f"Admin {'resumed' if action == 'resume' else 'cancelled'} the disputed exchange",
                      note, f"/proposal/{exchange['id']}")
    return await serialize_exchange(exchange, None)


async def add_offer(exchange: dict, user: dict, to_user_id: str, message: str, proposed_changes: Dict) -> Offer:
    """Negotiation message. Messages never change terms; use a counteroffer for that."""
    if exchange["status"] in TERMINAL_EXCHANGE_STATUSES:
        raise _conflict("This exchange is closed")
    await get_participant_or_403(exchange["id"], user)
    if to_user_id and to_user_id not in exchange["participant_ids"]:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Recipient is not in this exchange")
    values = (proposed_changes or {}).get("agreed_values")
    if values:
        await counteroffer(exchange, user, {k: float(v) for k, v in values.items()}, message)
        latest = await db.offers.find({"exchange_id": exchange["id"]}).sort("created_at", -1).to_list(1)
        return Offer(**clean_doc(dict(latest[0])))
    offer = {
        "id": f"of_{uuid4().hex[:12]}",
        "exchange_id": exchange["id"],
        "revision": exchange.get("revision", 1),
        "from_user_id": user["id"],
        "from_user_name": user["name"],
        "to_user_id": to_user_id or "",
        "message": message,
        "proposed_changes": {},
        "status": "open",
        "created_at": utc_now(),
    }
    await db.offers.insert_one(dict(offer))
    await notify_many([u for u in exchange["participant_ids"] if u != user["id"]], NotificationType.exchange,
                      f"New negotiation message from {user['name']}", message, f"/proposal/{exchange['id']}")
    return Offer(**clean_doc(offer))


async def exchange_history(exchange_id: str) -> Dict[str, List]:
    approvals = await db.exchange_approvals.find({"exchange_id": exchange_id}).sort("created_at", ASCENDING).to_list(300)
    offers = await db.offers.find({"exchange_id": exchange_id}).sort("created_at", ASCENDING).to_list(300)
    events = await db.exchange_events.find({"exchange_id": exchange_id}).sort("created_at", ASCENDING).to_list(500)
    return {
        "approvals": [ExchangeApproval(**clean_doc(dict(a))) for a in approvals],
        "offers": [Offer(**clean_doc(dict(o))) for o in offers],
        "events": [ExchangeEvent(**clean_doc(dict(e))) for e in events],
    }

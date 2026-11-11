"""Balancing payouts via the PayPal Payouts API (sandbox).

When a cycle completes, every participant who is owed money (balance < 0) is paid
|balance| from the marketplace's PayPal account.

Rules enforced here:
- A payout is only attempted for a *completed* exchange, never earlier.
- Ledger check: the payouts total can never exceed the balancing payments PayPal
  verified as captured for that exchange. Payouts can't be funded by money that
  was never collected.
- A payout counts as `success` only when PayPal itself reports the item as SUCCESS,
  either through the payouts API or a signature-verified webhook.
- Each attempt uses a unique `sender_batch_id`. PayPal rejects duplicates for 30
  days, so a retry cannot double-pay. A new attempt id is only used after PayPal
  has definitively failed the previous one.
- Receiver: the trader's saved PayPal email, falling back to their login email.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status as http_status

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.log import log_event
from models.common import NotificationType, PaymentStatus, PayoutStatus
from models.payouts import Payout
from services.compatibility import round_money
from services.notifications import notify
from services.payments import PayPalError, PayPalNotConfigured, _request, environment, is_configured

logger = logging.getLogger("barterx.payouts")

# PayPal item transaction_status → our status
_ITEM_STATUS = {
    "SUCCESS": PayoutStatus.success,
    "UNCLAIMED": PayoutStatus.unclaimed,
    "PENDING": PayoutStatus.processing,
    "ONHOLD": PayoutStatus.processing,
    "NEW": PayoutStatus.processing,
    "FAILED": PayoutStatus.failed,
    "RETURNED": PayoutStatus.failed,
    "BLOCKED": PayoutStatus.failed,
    "REFUNDED": PayoutStatus.failed,
    "REVERSED": PayoutStatus.failed,
    "DENIED": PayoutStatus.failed,
}
RETRYABLE = {PayoutStatus.failed.value, PayoutStatus.blocked.value, PayoutStatus.pending.value}
FINAL_OK = {PayoutStatus.success.value}


def _model(doc: dict) -> Payout:
    payload = clean_doc(dict(doc))
    payload["completed_at"] = clean_doc({"created_at": doc.get("completed_at")})["created_at"]
    return Payout(**payload)


async def _receiver(user_id: str) -> tuple[str, str]:
    user = await db.users.find_one({"id": user_id}, {"email": 1, "paypal_email": 1})
    if not user:
        return "", "missing"
    if user.get("paypal_email"):
        return user["paypal_email"], "paypal_email"
    return user["email"], "login_email"


async def _verified_collected(exchange_id: str) -> float:
    payments = await db.payments.find(
        {"exchange_id": exchange_id, "status": PaymentStatus.captured.value, "verified": True}
    ).to_list(50)
    return round_money(sum(float(p["amount"]) for p in payments))


def _sender_batch_id(exchange_id: str, participant_id: str, attempt: int) -> str:
    return f"bx-{exchange_id}-{participant_id}-a{attempt}"[:127]


async def _submit(doc: dict) -> dict:
    """Send one payout item to PayPal and record exactly what PayPal said."""
    now = utc_now()
    updates: Dict[str, Any] = {"updated_at": now}
    if not is_configured():
        updates.update({"status": PayoutStatus.blocked.value, "last_error": "PayPal sandbox credentials are not configured"})
        await db.payouts.update_one({"id": doc["id"]}, {"$set": updates})
        return {**doc, **updates}

    payload = {
        "sender_batch_header": {
            "sender_batch_id": doc["sender_batch_id"],
            "email_subject": "You received a BarterX balancing payout",
            "email_message": f"Balancing payout for completed BarterX exchange {doc['exchange_id']}.",
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "amount": {"value": f"{round_money(doc['amount']):.2f}", "currency": doc["currency"]},
                "receiver": doc["receiver_email"],
                "note": f"BarterX exchange {doc['exchange_id']}",
                "sender_item_id": doc["participant_id"],
            }
        ],
    }
    try:
        data = await _request("POST", "/v1/payments/payouts", payload)
    except PayPalNotConfigured as exc:
        updates.update({"status": PayoutStatus.blocked.value, "last_error": str(exc)})
    except PayPalError as exc:
        message = str(exc)
        # A duplicate sender_batch_id means PayPal already holds this attempt; never resend it.
        duplicate = "SENDER_BATCH_ID" in message.upper() or "DUPLICATE" in message.upper()
        updates.update(
            {
                "status": PayoutStatus.processing.value if duplicate else PayoutStatus.failed.value,
                "last_error": message[:500],
            }
        )
    else:
        header = data.get("batch_header") or {}
        updates.update(
            {
                "paypal_batch_id": header.get("payout_batch_id"),
                "status": PayoutStatus.processing.value,
                "last_error": None,
            }
        )
    await db.payouts.update_one({"id": doc["id"]}, {"$set": updates})
    merged = {**doc, **updates}
    if merged.get("paypal_batch_id"):
        merged = await refresh_from_paypal(merged)
    return merged


async def refresh_from_paypal(doc: dict) -> dict:
    """Pull the item status from PayPal (the only source of truth for a payout's outcome)."""
    if not doc.get("paypal_batch_id") or not is_configured():
        return doc
    try:
        data = await _request("GET", f"/v1/payments/payouts/{doc['paypal_batch_id']}")
    except PayPalError as exc:
        await db.payouts.update_one({"id": doc["id"]}, {"$set": {"last_error": str(exc)[:500], "updated_at": utc_now()}})
        return {**doc, "last_error": str(exc)[:500]}
    item = next(
        (
            row
            for row in data.get("items") or []
            if (row.get("payout_item") or {}).get("sender_item_id") == doc["participant_id"]
        ),
        (data.get("items") or [None])[0],
    )
    if not item:
        return doc
    return await apply_item_status(doc, item.get("transaction_status") or "", item.get("payout_item_id"), "payouts_api")


async def apply_item_status(doc: dict, transaction_status: str, item_id: Optional[str], source: str) -> dict:
    mapped = _ITEM_STATUS.get(transaction_status.upper(), PayoutStatus.processing)
    now = utc_now()
    updates: Dict[str, Any] = {
        "paypal_transaction_status": transaction_status.upper() or None,
        "status": mapped.value,
        "updated_at": now,
    }
    if item_id:
        updates["paypal_item_id"] = item_id
    if mapped == PayoutStatus.success:
        updates.update({"verified": True, "verification_source": source, "completed_at": now, "last_error": None})
    elif mapped == PayoutStatus.failed:
        updates.update({"verified": False, "last_error": f"PayPal reported payout item status {transaction_status}"})
    was_success = doc.get("status") == PayoutStatus.success.value
    await db.payouts.update_one({"id": doc["id"]}, {"$set": updates})
    merged = {**doc, **updates}
    if mapped == PayoutStatus.success and not was_success:
        await notify(
            doc["user_id"],
            NotificationType.payout,
            "Payout received",
            f"PayPal confirmed your {doc['amount']:.2f} {doc['currency']} balancing payout to {doc['receiver_email']}.",
            f"/proposal/{doc['exchange_id']}",
        )
    elif mapped == PayoutStatus.unclaimed and doc.get("status") != PayoutStatus.unclaimed.value:
        await notify(
            doc["user_id"],
            NotificationType.payout,
            "Payout waiting to be claimed",
            f"PayPal is holding {doc['amount']:.2f} {doc['currency']} for {doc['receiver_email']}. "
            "Sign up to PayPal with that email to claim it.",
            f"/proposal/{doc['exchange_id']}",
        )
    log_event(logger, "payout.status", payout_id=doc["id"], status=mapped.value, source=source)
    return merged


async def _prepare(exchange: dict, participant: dict, trigger: str) -> Optional[dict]:
    """Create or reuse the payout record for one owed participant, then submit it if appropriate."""
    owed = round_money(-(participant.get("balance_amount") or 0))
    if owed <= 0:
        return None
    existing = await db.payouts.find_one({"exchange_id": exchange["id"], "participant_id": participant["id"]})
    if existing and existing["status"] not in RETRYABLE:
        if existing["status"] in (PayoutStatus.processing.value, PayoutStatus.unclaimed.value):
            return await refresh_from_paypal(existing)
        return existing  # success: nothing to do

    # Ledger check: never pay out more than PayPal verified was collected for this exchange.
    already_paid = round_money(
        sum(
            float(p["amount"])
            for p in await db.payouts.find(
                {"exchange_id": exchange["id"], "status": {"$in": [PayoutStatus.success.value, PayoutStatus.processing.value, PayoutStatus.unclaimed.value]}}
            ).to_list(50)
            if p["participant_id"] != participant["id"]
        )
    )
    collected = await _verified_collected(exchange["id"])
    if round_money(already_paid + owed) - collected > 0.01:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail=(
                f"Payout blocked: {owed:.2f} {participant.get('currency', 'USD')} would exceed the "
                f"{collected:.2f} verified as collected for this exchange"
            ),
        )

    receiver, source = await _receiver(participant["user_id"])
    if not receiver:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="No email is available for this payout")

    now = utc_now()
    # A new attempt id only once PayPal definitively failed the previous attempt.
    attempt = (existing or {}).get("attempts", 0)
    reuse_id = existing and existing["status"] in (PayoutStatus.blocked.value, PayoutStatus.pending.value)
    if not reuse_id:
        attempt += 1
    doc = {
        "id": (existing or {}).get("id") or f"po_{exchange['id']}_{participant['user_id']}",
        "exchange_id": exchange["id"],
        "participant_id": participant["id"],
        "user_id": participant["user_id"],
        "amount": owed,
        "currency": participant.get("currency", "USD"),
        "receiver_email": receiver,
        "receiver_source": source,
        "sender_batch_id": (existing or {}).get("sender_batch_id") if reuse_id else _sender_batch_id(exchange["id"], participant["id"], attempt),
        "paypal_batch_id": None,
        "paypal_item_id": None,
        "paypal_transaction_status": None,
        "status": PayoutStatus.pending.value,
        "trigger": trigger,
        "verified": False,
        "verification_source": None,
        "attempts": max(attempt, 1),
        "environment": environment(),
        "last_error": None,
        "completed_at": None,
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }
    await db.payouts.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
    log_event(logger, "payout.submitting", payout_id=doc["id"], trigger=trigger, amount=owed, attempt=doc["attempts"])
    return await _submit(doc)


async def payout_completed_exchange(exchange_id: str) -> List[dict]:
    """Automatic payouts after completion. Never raises: failures are recorded and can be claimed later."""
    exchange = await db.exchanges.find_one({"id": exchange_id})
    if not exchange or exchange.get("status") != "completed":
        return []
    results = []
    for participant in await db.exchange_participants.find({"exchange_id": exchange_id}).to_list(10):
        try:
            result = await _prepare(exchange, participant, "automatic")
        except HTTPException as exc:
            log_event(logger, "payout.auto_blocked", exchange_id=exchange_id, participant_id=participant["id"], reason=str(exc.detail))
            continue
        except Exception as exc:  # completion must never be undone by a payout problem
            log_event(logger, "payout.auto_error", exchange_id=exchange_id, error=str(exc)[:300])
            continue
        if result:
            results.append(result)
    return results


async def claim_payout(exchange: dict, participant: dict) -> Payout:
    if exchange.get("status") != "completed":
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Payouts are only sent once every participant has confirmed fulfilment",
        )
    if round_money(-(participant.get("balance_amount") or 0)) <= 0:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="You are not owed a payout on this exchange")
    if not is_configured():
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="PayPal sandbox credentials are not configured, so payouts cannot be sent yet",
        )
    result = await _prepare(exchange, participant, "claim")
    return _model(result)


async def list_for_exchange(exchange_id: str) -> List[Payout]:
    docs = await db.payouts.find({"exchange_id": exchange_id}).sort([("created_at", 1)]).to_list(20)
    return [_model(doc) for doc in docs]


async def refresh_payout(payout_id: str, user: dict) -> Payout:
    doc = await db.payouts.find_one({"id": payout_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Payout not found")
    if doc["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="This payout is not yours")
    return _model(await refresh_from_paypal(doc))


async def handle_payout_webhook(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Apply an (already signature-verified) PAYMENT.PAYOUTS-ITEM.* event. Returns None if not a payout event."""
    event_type = event.get("event_type", "")
    if not event_type.startswith("PAYMENT.PAYOUTS-ITEM."):
        return None
    resource = event.get("resource") or {}
    item_id = resource.get("payout_item_id")
    doc = await db.payouts.find_one({"paypal_item_id": item_id}) if item_id else None
    if not doc and resource.get("payout_batch_id"):
        doc = await db.payouts.find_one({"paypal_batch_id": resource["payout_batch_id"]})
    if not doc:
        return {"status": "ignored", "reason": "no matching payout", "event_type": event_type}
    await apply_item_status(doc, resource.get("transaction_status") or "", item_id, "webhook")
    return {"status": "processed", "event_type": event_type, "payout_id": doc["id"]}

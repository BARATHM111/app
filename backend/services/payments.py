"""PayPal REST (sandbox) balancing payments.

Rules this module enforces by construction:
- a payment is only ever created because a signed-in participant explicitly asked for
  it (the request is the authorisation),
- a payment is only ever marked successful from PayPal's own server-side answer —
  the capture API response or a signature-verified webhook — never from a redirect,
- a failed or unverified capture is recorded as a failure, never retried quietly.

PayPal is NOT an escrow service: captured sandbox funds settle to the marketplace
sandbox merchant account and the ledger records who owes what.
"""

import base64
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import HTTPException, status as http_status

from lib.db import db
from lib.dates import clean_doc, utc_now
from models.common import NotificationType, PaymentStatus
from models.payments import Payment, PaymentConfigStatus, PaymentInitResponse
from services.compatibility import round_money
from services.notifications import notify

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
PENDING_STATUSES = (PaymentStatus.created.value, PaymentStatus.approved.value)
_token_cache: Dict[str, Any] = {"token": None, "expires_at": 0.0}


class PayPalNotConfigured(RuntimeError):
    pass


class PayPalError(RuntimeError):
    pass


def api_base() -> str:
    return os.environ.get("PAYPAL_API_BASE", SANDBOX_BASE).rstrip("/")


def environment() -> str:
    return "sandbox" if "sandbox" in api_base() else "live"


def client_id() -> str:
    return os.environ.get("PAYPAL_CLIENT_ID", "")


def client_secret() -> str:
    return os.environ.get("PAYPAL_SECRET", "")


def webhook_id() -> str:
    return os.environ.get("PAYPAL_WEBHOOK_ID", "")


def is_configured() -> bool:
    return bool(client_id() and client_secret())


def config_status() -> PaymentConfigStatus:
    configured = is_configured()
    return PaymentConfigStatus(
        configured=configured,
        environment=environment(),
        detail=(
            f"PayPal {environment()} credentials are configured."
            if configured
            else "PayPal sandbox credentials are missing — add PAYPAL_CLIENT_ID and PAYPAL_SECRET "
            "to the backend environment. Payment endpoints stay disabled until then."
        ),
    )


async def _access_token() -> str:
    if not is_configured():
        raise PayPalNotConfigured("PayPal sandbox credentials are not configured")
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 30:
        return _token_cache["token"]
    basic = base64.b64encode(f"{client_id()}:{client_secret()}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{api_base()}/v1/oauth2/token",
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"},
        )
    if response.status_code != 200:
        raise PayPalError(f"PayPal token request failed ({response.status_code}): {response.text[:300]}")
    payload = response.json()
    _token_cache["token"] = payload["access_token"]
    _token_cache["expires_at"] = now + int(payload.get("expires_in", 3000))
    return _token_cache["token"]


async def _request(
    method: str, path: str, payload: Dict[str, Any] | None = None, request_id: str | None = None
) -> Dict[str, Any]:
    """`request_id` becomes PayPal-Request-Id, PayPal's idempotency key: a retried call with the
    same id returns the original result instead of creating or capturing twice."""
    token = await _access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.request(method, f"{api_base()}{path}", headers=headers, json=payload if method != "GET" else None)
    if response.status_code >= 400:
        raise PayPalError(f"PayPal {method} {path} failed ({response.status_code}): {response.text[:400]}")
    return response.json() if response.content else {}


async def create_order(
    amount: float,
    currency: str,
    reference_id: str,
    custom_id: str,
    description: str,
    return_url: str,
    cancel_url: str,
    request_id: str | None = None,
) -> Tuple[str, str]:
    """Create a CAPTURE order and return (order_id, approval_url)."""
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "reference_id": reference_id,
                "custom_id": custom_id,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": f"{round_money(amount):.2f}"},
            }
        ],
        "application_context": {
            "brand_name": "BarterX",
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
            "return_url": return_url,
            "cancel_url": cancel_url,
        },
    }
    data = await _request("POST", "/v2/checkout/orders", payload, request_id=request_id)
    approval_url = next(
        (link["href"] for link in data.get("links", []) if link.get("rel") in ("approve", "payer-action")),
        "",
    )
    if not data.get("id") or not approval_url:
        raise PayPalError("PayPal did not return an approval link for the order")
    return data["id"], approval_url


async def capture_order(order_id: str, request_id: str | None = None) -> Dict[str, Any]:
    return await _request("POST", f"/v2/checkout/orders/{order_id}/capture", {}, request_id=request_id)


async def get_order(order_id: str) -> Dict[str, Any]:
    return await _request("GET", f"/v2/checkout/orders/{order_id}")


async def verify_webhook(headers: Dict[str, str], event: Dict[str, Any]) -> bool:
    """Ask PayPal whether this webhook really came from PayPal."""
    if not webhook_id():
        raise PayPalNotConfigured("PAYPAL_WEBHOOK_ID is not configured, so webhooks cannot be verified")
    payload = {
        "transmission_id": headers.get("paypal-transmission-id", ""),
        "transmission_time": headers.get("paypal-transmission-time", ""),
        "cert_url": headers.get("paypal-cert-url", ""),
        "auth_algo": headers.get("paypal-auth-algo", ""),
        "transmission_sig": headers.get("paypal-transmission-sig", ""),
        "webhook_id": webhook_id(),
        "webhook_event": event,
    }
    data = await _request("POST", "/v1/notifications/verify-webhook-signature", payload)
    return data.get("verification_status") == "SUCCESS"


def _captured_amount(capture: Dict[str, Any]) -> Tuple[float, str]:
    amount = capture.get("amount") or {}
    return round_money(float(amount.get("value") or 0)), str(amount.get("currency_code") or "")


async def _payment_model(doc: dict) -> Payment:
    payload = clean_doc(dict(doc))
    for field in ("authorized_at", "captured_at"):
        payload[field] = clean_doc({"created_at": doc.get(field)})["created_at"]
    return Payment(**payload)


async def find_payment(payment_id: str) -> dict:
    doc = await db.payments.find_one({"id": payment_id})
    if not doc:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return doc


async def initiate_payment(
    exchange: dict,
    participant: dict,
    user: dict,
    return_url: str,
    cancel_url: str,
) -> PaymentInitResponse:
    """Called only from an explicit, authenticated user action."""
    balance = round_money(participant.get("balance_amount") or 0)
    if balance <= 0:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="No balancing payment is required from you on this exchange",
        )
    if exchange["status"] not in ("approved", "payment_pending"):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Every participant must approve the same revision before any payment is initiated",
        )

    revision = exchange.get("revision", 1)
    existing = await db.payments.find_one({"exchange_id": exchange["id"], "participant_id": participant["id"]})
    if existing and existing.get("status") == PaymentStatus.captured.value and existing.get("verified"):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Your balancing payment for this exchange is already captured and verified",
        )
    # Idempotency: an open order for the same revision and amount is reused, never duplicated.
    if (
        existing
        and existing.get("status") == PaymentStatus.created.value
        and existing.get("revision") == revision
        and abs(round_money(existing.get("amount") or 0) - balance) < 0.005
        and existing.get("approval_url")
    ):
        return PaymentInitResponse(
            payment=await _payment_model(existing),
            approval_url=existing["approval_url"],
            paypal_order_id=existing["paypal_order_id"],
            environment=environment(),
        )

    reference = f"{exchange['id']}:{participant['id']}"
    order_id, approval_url = await create_order(
        amount=balance,
        currency=participant.get("currency", "USD"),
        reference_id=reference,
        custom_id=participant["id"],
        description=f"BarterX balancing payment for exchange {exchange['id']}",
        return_url=return_url,
        cancel_url=cancel_url,
        request_id=f"bx-order-{participant['id']}-r{revision}-{int(balance * 100)}",
    )

    now = utc_now()
    doc = {
        "id": (existing or {}).get("id") or f"pay_{exchange['id']}_{participant['user_id']}",
        "exchange_id": exchange["id"],
        "participant_id": participant["id"],
        "user_id": user["id"],
        "amount": balance,
        "currency": participant.get("currency", "USD"),
        "provider": "paypal",
        "environment": environment(),
        "paypal_order_id": order_id,
        "approval_url": approval_url,
        "revision": revision,
        "capturing": False,
        "paypal_capture_id": None,
        "status": PaymentStatus.created.value,
        "verified": False,
        "verification_source": None,
        "authorized_at": None,
        "captured_at": None,
        "last_error": None,
        "created_at": (existing or {}).get("created_at") or now,
        "updated_at": now,
    }
    await db.payments.update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)
    from services.exchanges import refresh_exchange_state  # local import keeps modules acyclic

    await refresh_exchange_state(exchange["id"])  # approved -> payment_pending
    return PaymentInitResponse(
        payment=await _payment_model(doc),
        approval_url=approval_url,
        paypal_order_id=order_id,
        environment=environment(),
    )


async def apply_capture_result(payment: dict, capture_payload: Dict[str, Any], source: str) -> dict:
    """Record what PayPal actually said. Success is only ever PayPal's own word."""
    order = capture_payload or {}
    order_status = order.get("status")
    captures = []
    for unit in order.get("purchase_units") or []:
        captures.extend(((unit.get("payments") or {}).get("captures") or []))
    completed = next((c for c in captures if c.get("status") == "COMPLETED"), None)

    now = utc_now()
    updates: Dict[str, Any] = {"updated_at": now}
    if order_status == "COMPLETED" and completed:
        amount, currency = _captured_amount(completed)
        if abs(amount - round_money(payment["amount"])) > 0.01 or (
            currency and currency != payment["currency"]
        ):
            updates.update(
                {
                    "status": PaymentStatus.failed.value,
                    "verified": False,
                    "last_error": (
                        f"Captured {amount} {currency} does not match the agreed "
                        f"{round_money(payment['amount'])} {payment['currency']}"
                    ),
                }
            )
        else:
            updates.update(
                {
                    "status": PaymentStatus.captured.value,
                    "paypal_capture_id": completed.get("id"),
                    "verified": True,
                    "verification_source": source,
                    "captured_at": now,
                    "last_error": None,
                }
            )
    elif any(c.get("status") == "PENDING" for c in captures):
        updates.update({"status": PaymentStatus.pending.value, "verified": False, "last_error": "PayPal is holding the capture (PENDING)"})
    else:
        updates.update(
            {
                "status": PaymentStatus.failed.value,
                "verified": False,
                "last_error": f"PayPal reported order status {order_status!r}",
            }
        )

    await db.payments.update_one({"id": payment["id"]}, {"$set": updates})
    updated = {**payment, **updates}

    if updated.get("verified"):
        exchange = await db.exchanges.find_one({"id": payment["exchange_id"]})
        if exchange:
            await notify(
                payment["user_id"],
                NotificationType.payment,
                "Balancing payment verified",
                f"PayPal confirmed {payment['amount']:.2f} {payment['currency']} for exchange {payment['exchange_id']}.",
                f"/proposal/{payment['exchange_id']}",
            )
        from services.exchanges import refresh_exchange_state  # local import keeps the modules acyclic

        await refresh_exchange_state(payment["exchange_id"])
    return updated


async def capture_payment(payment_id: str, user: dict) -> Payment:
    """Server-side capture after the payer approved on PayPal. The browser's word is never trusted:
    success is recorded only from PayPal's capture response (or a verified webhook / order lookup)."""
    payment = await find_payment(payment_id)
    if payment["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You can only capture your own balancing payment")
    if payment.get("status") == PaymentStatus.captured.value and payment.get("verified"):
        return await _payment_model(payment)  # idempotent
    if payment.get("status") == PaymentStatus.cancelled.value:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="This payment was cancelled. Start a new one for the current terms.")
    exchange = await db.exchanges.find_one({"id": payment["exchange_id"]}) or {}
    if payment.get("revision", exchange.get("revision", 1)) != exchange.get("revision", 1):
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="The exchange terms changed after this order was created")
    if not payment.get("paypal_order_id"):
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="This payment has no PayPal order")

    # Duplicate-capture guard: only one capture may be in flight per payment.
    lock = await db.payments.update_one(
        {"id": payment_id, "capturing": {"$ne": True}, "status": {"$in": [PaymentStatus.created.value, PaymentStatus.approved.value, PaymentStatus.pending.value, PaymentStatus.failed.value]}},
        {"$set": {"capturing": True, "updated_at": utc_now()}},
    )
    if lock.modified_count == 0:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="A capture for this payment is already in progress")
    try:
        try:
            payload = await capture_order(payment["paypal_order_id"], request_id=f"bx-capture-{payment_id}")
        except PayPalError as exc:
            if "ORDER_ALREADY_CAPTURED" in str(exc):
                payload = await get_order(payment["paypal_order_id"])  # recover the real result
            else:
                raise
    except PayPalNotConfigured as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PayPalError as exc:
        await db.payments.update_one({"id": payment_id}, {"$set": {"last_error": str(exc)[:500], "updated_at": utc_now()}})
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    finally:
        await db.payments.update_one({"id": payment_id}, {"$set": {"capturing": False}})

    updated = await apply_capture_result(payment, payload, "capture_api_response")
    return await _payment_model(updated)


async def cancel_payment(payment_id: str, user: dict) -> Payment:
    """Payer abandoned PayPal approval (cancel_url) or changed their mind before capture."""
    payment = await find_payment(payment_id)
    if payment["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You can only cancel your own payment")
    if payment.get("status") == PaymentStatus.captured.value:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="A captured payment cannot be cancelled here")
    await db.payments.update_one(
        {"id": payment_id, "status": {"$ne": PaymentStatus.captured.value}},
        {"$set": {"status": PaymentStatus.cancelled.value, "last_error": "Cancelled by payer before capture", "updated_at": utc_now()}},
    )
    from services.exchanges import refresh_exchange_state

    await refresh_exchange_state(payment["exchange_id"])
    return await _payment_model(await find_payment(payment_id))


async def sync_payment(payment_id: str, user: dict) -> Payment:
    """Status synchronisation: read the order from PayPal and record what it reports."""
    payment = await find_payment(payment_id)
    if payment["user_id"] != user["id"]:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="You can only sync your own payment")
    if payment.get("verified") or not payment.get("paypal_order_id"):
        return await _payment_model(payment)
    try:
        order = await get_order(payment["paypal_order_id"])
    except PayPalNotConfigured as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PayPalError as exc:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    if order.get("status") == "COMPLETED":
        return await _payment_model(await apply_capture_result(payment, order, "order_sync"))
    if order.get("status") == "APPROVED" and payment.get("status") == PaymentStatus.created.value:
        await db.payments.update_one({"id": payment_id}, {"$set": {"status": PaymentStatus.approved.value, "authorized_at": utc_now()}})
    return await _payment_model(await find_payment(payment_id))


async def handle_webhook(headers: Dict[str, str], event: Dict[str, Any]) -> Dict[str, Any]:
    """Signature-verified PayPal webhook. Unverified events are rejected, never trusted."""
    try:
        verified = await verify_webhook(headers, event)
    except PayPalNotConfigured as exc:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PayPalError as exc:
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if not verified:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature verification failed — event ignored",
        )

    from services.payouts import handle_payout_webhook  # local import: payouts imports this module

    payout_result = await handle_payout_webhook(event)
    if payout_result is not None:
        return payout_result

    event_type = event.get("event_type", "")
    resource = event.get("resource") or {}
    order_id = (
        (resource.get("supplementary_data") or {}).get("related_ids", {}).get("order_id")
        or resource.get("id")
    )
    payment = None
    if order_id:
        payment = await db.payments.find_one({"paypal_order_id": order_id})
    if not payment and resource.get("custom_id"):
        payment = await db.payments.find_one({"participant_id": resource["custom_id"]})

    if not payment:
        return {"status": "ignored", "reason": "no matching payment", "event_type": event_type}

    if event_type == "CHECKOUT.ORDER.APPROVED":
        await db.payments.update_one(
            {"id": payment["id"]},
            {
                "$set": {
                    "status": PaymentStatus.approved.value,
                    "authorized_at": utc_now(),
                    "updated_at": utc_now(),
                }
            },
        )
        return {"status": "processed", "event_type": event_type, "payment_id": payment["id"]}

    if event_type == "PAYMENT.CAPTURE.COMPLETED":
        if payment.get("verified"):
            return {"status": "already_verified", "payment_id": payment["id"]}
        await apply_capture_result(
            payment,
            {
                "status": "COMPLETED",
                "purchase_units": [
                    {"payments": {"captures": [resource]}},
                ],
            },
            "webhook",
        )
        return {"status": "processed", "event_type": event_type, "payment_id": payment["id"]}

    if event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"):
        new_status = PaymentStatus.refunded.value if "REFUND" in event_type or "REVERS" in event_type else PaymentStatus.failed.value
        await db.payments.update_one(
            {"id": payment["id"]},
            {"$set": {"status": new_status, "verified": False, "updated_at": utc_now(), "last_error": event_type}},
        )
        return {"status": "processed", "event_type": event_type, "payment_id": payment["id"]}

    return {"status": "ignored", "event_type": event_type}

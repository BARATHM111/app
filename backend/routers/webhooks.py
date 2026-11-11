"""WebhooksModule — inbound PayPal events.

Verification is mandatory: an event whose signature PayPal does not confirm is
rejected with 400 and never touches payment state.
"""

import logging

from fastapi import APIRouter, Request

from lib.log import log_event
from services.payments import handle_webhook

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])
logger = logging.getLogger("barterx.webhooks")


@router.post("/paypal", status_code=200)
async def paypal_webhook(request: Request):
    headers = {key.lower(): value for key, value in request.headers.items()}
    event = await request.json()
    result = await handle_webhook(headers, event)
    log_event(logger, "webhook.paypal", result=result.get("status"), event_type=event.get("event_type"))
    return result

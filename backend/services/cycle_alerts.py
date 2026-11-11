"""Cycle alerts: tell traders the moment a change completes a new exchange cycle that includes them.

Triggered after a listing or want is created or updated (as a background task, so the
write itself stays fast). Discovery is the same deterministic graph engine. Each cycle
key is announced once: the unique `cycle_alerts.cycle_key` index makes this race-safe.
"""

import logging
from typing import Optional

from pymongo.errors import DuplicateKeyError

from lib.db import db
from lib.dates import utc_now
from lib.log import log_event
from models.common import NotificationType
from services.notifications import notify

logger = logging.getLogger("barterx.cycle_alerts")


async def alert_new_cycles(trigger_user_id: Optional[str] = None, trigger_label: str = "") -> int:
    """Notify every participant of each newly discovered cycle. Returns the number of new cycles announced."""
    from services.graph import discover_cycles  # local import keeps module load order simple

    try:
        cycles = await discover_cycles(max_nodes=3, limit=200)
    except Exception as exc:  # an alert failure must never break the write that triggered it
        log_event(logger, "cycle_alert.discovery_failed", error=str(exc)[:300])
        return 0

    announced = 0
    for cycle in cycles:
        participant_ids = [p.user_id for p in cycle.participants]
        if trigger_user_id and trigger_user_id not in participant_ids:
            continue
        try:
            await db.cycle_alerts.insert_one(
                {
                    "cycle_key": cycle.key,
                    "participant_ids": participant_ids,
                    "trigger_user_id": trigger_user_id,
                    "notified_at": utc_now(),
                }
            )
        except DuplicateKeyError:
            continue  # already announced

        names = {p.user_id: p.user_name for p in cycle.participants}
        trigger_name = names.get(trigger_user_id or "", "")
        for participant in cycle.participants:
            if trigger_user_id and participant.user_id == trigger_user_id:
                body = f"Your {trigger_label or 'change'} completes a {cycle.cycle_type}-party cycle."
            elif trigger_name:
                body = f"{trigger_name}'s {trigger_label or 'update'} completes a {cycle.cycle_type}-party cycle with you."
            else:
                body = f"A {cycle.cycle_type}-party cycle that includes you is now possible."
            body += (
                f" You would give {participant.gives_listing_title} and receive "
                f"{participant.receives_listing_title}. Review it and propose it if it suits you."
            )
            await notify(
                participant.user_id,
                NotificationType.cycle,
                f"New {cycle.cycle_type}-party exchange cycle found",
                body,
                "/cycles",
            )
        announced += 1
        log_event(logger, "cycle_alert.sent", cycle_key=cycle.key, participants=len(participant_ids))
    return announced


async def after_listing_change(listing: dict, *, created: bool) -> None:
    from services.embeddings import embed_listing

    await embed_listing(listing)
    label = f"new listing \u201c{listing['title']}\u201d" if created else f"updated listing \u201c{listing['title']}\u201d"
    await alert_new_cycles(listing["owner_id"], label)


async def after_want_change(want: dict) -> None:
    from services.embeddings import embed_want

    await embed_want(want)
    await alert_new_cycles(want["user_id"], f"want \u201c{want['title']}\u201d")

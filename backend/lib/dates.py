"""Server-side date/time helpers.

The pod clock is UTC. BSON stores UTC but motor hands back *naive* datetimes, so
every read passes through `as_utc` before it is compared or serialised — an aware
and a naive datetime can never be subtracted (that raises TypeError → 500).
"""

import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def today_iso(tz: str | None = None) -> str:
    """Today's date as YYYY-MM-DD in `tz` (default: APP_TZ env, else UTC)."""
    zone = tz or os.environ.get("APP_TZ", "UTC")
    return datetime.now(ZoneInfo(zone)).strftime("%Y-%m-%d")


def utc_now() -> datetime:
    """Aware UTC 'now' — the only source of current time in the backend."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Normalise a motor datetime (naive UTC) to an aware UTC datetime."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalise_timestamps(doc: dict, *fields: str) -> dict:
    """In-place normalise the named datetime fields of a Mongo document."""
    for field in fields:
        if field in doc:
            doc[field] = as_utc(doc[field])
    return doc


DEFAULT_TIMESTAMP_FIELDS = ("created_at", "updated_at")


def clean_doc(doc: dict) -> dict:
    """Normalise created_at/updated_at on a Mongo document before model construction."""
    return normalise_timestamps(doc, *DEFAULT_TIMESTAMP_FIELDS)

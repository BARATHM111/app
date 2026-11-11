"""Deterministic compatibility rules — the gate every candidate must pass.

Nothing here is probabilistic: the AI layer never decides whether a trade is
valid, only how to describe it.
"""

from dataclasses import dataclass, field

from lib.embeddings import cosine_similarity, embed_text, listing_text, want_text

# Exchanges in these states hold a claim on their listings.
ACTIVE_EXCHANGE_STATUSES = (
    "proposed",
    "pending_approval",
    "approved",
    "payment_pending",
    "ready_for_fulfillment",
    "fulfillment_in_progress",
    "disputed",
)


def round_money(value: float) -> float:
    """All money values are rounded to 2 decimals at every boundary."""
    return round(float(value) + 0.0, 2)


def value_closeness(a: float, b: float) -> float:
    """1.0 for identical values, decaying linearly to 0.0 — deterministic, no AI."""
    a, b = float(a), float(b)
    largest = max(a, b)
    if largest <= 0:
        return 1.0
    return round(max(0.0, 1.0 - min(1.0, abs(a - b) / largest)), 4)


@dataclass
class CompatibilityResult:
    ok: bool
    blockers: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)


def check_compatibility(listing: dict, want: dict) -> CompatibilityResult:
    """Can `listing` fill `want`? Purely deterministic on type/category/currency/value."""
    blockers: list[str] = []
    strengths: list[str] = []

    target_type = want.get("target_type", "any")
    if target_type != "any" and listing.get("type") != target_type:
        blockers.append(
            f"Type mismatch: the want asks for {target_type}, this listing is {listing.get('type')}"
        )
    else:
        strengths.append(f"Offers the requested kind of value ({listing.get('type')})")

    want_category = (want.get("category") or "").strip()
    listing_category = (listing.get("category") or "").strip()
    if want_category and listing_category.lower() != want_category.lower():
        blockers.append(f"Category mismatch: wants {want_category}, listing is {listing_category}")
    elif want_category:
        strengths.append(f"Matches the requested category ({listing_category})")

    if listing.get("currency") != want.get("currency"):
        blockers.append(
            f"Currency mismatch: want is in {want.get('currency')}, listing is in {listing.get('currency')}"
        )

    value = float(listing.get("estimated_value") or 0)
    low = float(want.get("min_value") or 0)
    high = float(want.get("max_value") or 0)
    if value < low or value > high:
        blockers.append(
            f"Value {value:.2f} {want.get('currency')} sits outside the accepted "
            f"{low:.2f}–{high:.2f} range"
        )
    else:
        strengths.append(f"Value {value:.2f} is inside the accepted {low:.2f}–{high:.2f} range")

    if listing.get("owner_id") == want.get("user_id"):
        blockers.append("You cannot trade your own listing into your own want")

    if listing.get("status") != "active":
        blockers.append(f"Listing is not active (status: {listing.get('status')})")

    return CompatibilityResult(ok=not blockers, blockers=blockers, strengths=strengths)


def listing_want_semantic_score(listing: dict, want: dict) -> float:
    """Cosine similarity between the listing and the want embeddings (local, deterministic)."""
    return round(
        cosine_similarity(
            embed_text(listing_text(listing.get("title", ""), listing.get("description", ""), listing.get("category", ""), listing.get("tags"))),
            embed_text(want_text(want.get("title", ""), want.get("description", ""), want.get("category", ""), want.get("keywords"))),
        ),
        4,
    )


def reference_value(want: dict) -> float:
    """The value a want is judged against: its linked listing, else the range midpoint."""
    offered = want.get("offered_value")
    if offered:
        return float(offered)
    return round_money((float(want.get("min_value") or 0) + float(want.get("max_value") or 0)) / 2)

"""Deterministic direct-match scoring.

    score = w_semantic * semantic + w_category * category + w_value * value + w_location * location

Every component is normalised to [0, 1]. The default weights are 0.45 / 0.25 / 0.20 / 0.10, and
they can be changed with MATCH_WEIGHTS ("semantic=0.45,category=0.25,value=0.20,location=0.10").
They are renormalised to sum to 1.

Hard filters run first: availability, ownership, type, currency, condition and a
local-only location preference. A failed filter means "not a candidate", whatever the score.

A score ranks recommendations. It does not prove an exchange is fair or feasible; that is
decided only when every participant approves the same proposal version.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

DEFAULT_WEIGHTS: Dict[str, float] = {"semantic": 0.45, "category": 0.25, "value": 0.20, "location": 0.10}
DEFAULT_EDGE_THRESHOLD = 0.55

# Higher rank = better condition. Services have no condition.
CONDITION_RANK: Dict[str, int] = {
    "for parts": 0,
    "fair": 1,
    "good": 2,
    "excellent": 3,
    "like new": 4,
    "new": 5,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def parse_weights(raw: Optional[str]) -> Dict[str, float]:
    """Parse "semantic=0.45,category=0.25,..." and renormalise. Invalid input → defaults."""
    if not raw:
        return dict(DEFAULT_WEIGHTS)
    weights = dict(DEFAULT_WEIGHTS)
    try:
        for part in raw.split(","):
            if not part.strip():
                continue
            key, value = part.split("=", 1)
            key = key.strip().lower()
            if key not in DEFAULT_WEIGHTS:
                raise ValueError(key)
            weights[key] = max(0.0, float(value))
    except ValueError:
        return dict(DEFAULT_WEIGHTS)
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {key: round(value / total, 6) for key, value in weights.items()}


@dataclass(frozen=True)
class ScoringConfig:
    weights: Dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    edge_threshold: float = DEFAULT_EDGE_THRESHOLD

    @classmethod
    def from_env(cls) -> "ScoringConfig":
        try:
            threshold = _clamp(float(os.environ.get("MATCH_EDGE_THRESHOLD", DEFAULT_EDGE_THRESHOLD)))
        except ValueError:
            threshold = DEFAULT_EDGE_THRESHOLD
        return cls(weights=parse_weights(os.environ.get("MATCH_WEIGHTS")), edge_threshold=threshold)


@dataclass
class PairScore:
    ok: bool
    score: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)
    blockers: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)


def _city(location: Optional[str]) -> str:
    return (location or "").split(",")[0].strip().lower()


def _is_remote(listing: dict) -> bool:
    return listing.get("type") == "services" and "remote" in (listing.get("location") or "").lower()


def category_component(listing: dict, want: dict) -> float:
    wanted = (want.get("category") or "").strip().lower()
    offered = (listing.get("category") or "").strip().lower()
    if not wanted:
        return 0.6  # the trader accepts any category
    return 1.0 if wanted == offered else 0.0


def value_component(listing: dict, want: dict) -> float:
    """1.0 inside the accepted range. Outside it, the score decays linearly to 0 at half a range-width away."""
    value = float(listing.get("estimated_value") or 0)
    low = float(want.get("min_value") or 0)
    high = float(want.get("max_value") or 0)
    if low <= value <= high:
        return 1.0
    width = max(high - low, high, 1.0) * 0.5
    distance = (low - value) if value < low else (value - high)
    return round(_clamp(1.0 - distance / width), 4)


def location_component(listing: dict, want_location: str) -> float:
    if _is_remote(listing):
        return 1.0
    mine, theirs = _city(want_location), _city(listing.get("location"))
    if not mine or not theirs:
        return 0.5  # unknown, so neither rewarded nor punished
    return 1.0 if mine == theirs else 0.25


def hard_filters(listing: dict, want: dict, want_location: str, reserved: frozenset) -> List[str]:
    blockers: List[str] = []
    if listing.get("status") != "active":
        blockers.append(f"Listing is not available (status: {listing.get('status')})")
    if listing.get("id") in reserved:
        blockers.append("Listing is reserved by another active exchange")
    if listing.get("owner_id") == want.get("user_id"):
        blockers.append("A trader cannot fill their own want")
    target = want.get("target_type") or "any"
    if target != "any" and listing.get("type") != target:
        blockers.append(f"Type mismatch: wants {target}, listing is {listing.get('type')}")
    if (listing.get("currency") or "USD") != (want.get("currency") or "USD"):
        blockers.append("Currency mismatch")
    minimum = (want.get("min_condition") or "").strip().lower()
    if minimum and listing.get("type") == "goods":
        have = CONDITION_RANK.get((listing.get("condition") or "").strip().lower())
        if have is None or have < CONDITION_RANK.get(minimum, 0):
            blockers.append(f"Condition '{listing.get('condition') or 'unknown'}' is below the required '{want.get('min_condition')}'")
    if (want.get("location_preference") or "any") == "local" and not _is_remote(listing):
        if not _city(want_location) or _city(want_location) != _city(listing.get("location")):
            blockers.append("The want is local-only and this listing is elsewhere")
    return blockers


def score_pair(
    listing: dict,
    want: dict,
    semantic: Optional[float],
    *,
    want_location: str = "",
    reserved: frozenset = frozenset(),
    config: Optional[ScoringConfig] = None,
) -> PairScore:
    """Score one (listing, want) pair. `semantic=None` means the embedding provider failed, which counts as 0."""
    config = config or ScoringConfig.from_env()
    blockers = hard_filters(listing, want, want_location, reserved)
    components = {
        "semantic": round(_clamp(semantic or 0.0), 4),
        "category": category_component(listing, want),
        "value": value_component(listing, want),
        "location": location_component(listing, want_location),
    }
    weights = config.weights
    score = round(sum(weights[key] * components[key] for key in DEFAULT_WEIGHTS), 4)
    reasons = [
        f"Semantic similarity {components['semantic']:.2f}" + ("" if semantic is not None else " (embedding unavailable)"),
        "Same category" if components["category"] == 1.0 else ("Any category accepted" if components["category"] > 0 else "Different category"),
        "Value inside the accepted range" if components["value"] == 1.0 else f"Value outside the range (closeness {components['value']:.2f})",
        {1.0: "Same city or remote service", 0.5: "Location unknown", 0.25: "Different city"}.get(components["location"], "Location"),
    ]
    return PairScore(ok=not blockers, score=score, components=components, blockers=blockers, reasons=reasons)

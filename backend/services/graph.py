"""Deterministic graph engine: compatibility edges, bounded-DFS cycle discovery and ranking.

There is no AI and no randomness here. Given the same listings, wants and scores it always
returns the same cycles in the same order. A cycle is a *candidate* (status "discovered").
It becomes an exchange only when a participant proposes it, and it never becomes an approved
exchange automatically.

Graph:  nodes = users.  Edge A -> B  <=>  one of A's active listings satisfies one of B's open wants
        (passes the hard filters and scores >= the configured threshold). Each edge records the
        exact listing and want that establish it. Per (A, B) the best edge is kept.

Cycles: bounded DFS of length 2..max_len. Each cycle is rooted at its smallest user id, so
        every cycle is found once. Rules: no repeated participant, no self-exchange, no inactive
        or reserved listing, no duplicate listing, every participant receives something they want,
        every edge >= threshold, and previously rejected cycles are excluded.

Ranking: higher minimum edge score, then higher average edge score, then smaller total value
         difference, then fewer participants, then cycle id.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from lib.db import db
from lib.dates import utc_now
from models.wants import Cycle, CycleParticipant, GraphEdge
from services.compatibility import listing_want_semantic_score, round_money
from services.embeddings import pair_scores
from services.reservations import reserved_listing_ids
from services.scoring import ScoringConfig, score_pair

MAX_LISTINGS_SCANNED = 2000
MAX_WANTS_SCANNED = 2000
SUPPORTED_MAX_LEN = 3

Edges = Dict[Tuple[str, str], dict]


# ---------------------------------------------------------------- pure functions (unit-tested)

def build_edges(
    listings: Sequence[dict],
    wants: Sequence[dict],
    users: Dict[str, dict],
    *,
    scores: Optional[Dict[Tuple[str, str], float]] = None,
    reserved: frozenset = frozenset(),
    config: Optional[ScoringConfig] = None,
) -> Edges:
    """Best qualifying edge per (giver, receiver). `scores=None` uses the pure local embedder (for tests)."""
    config = config or ScoringConfig.from_env()
    best: Edges = {}
    for want in sorted(wants, key=lambda w: w["id"]):
        if want.get("status", "open") != "open":
            continue
        receiver = want["user_id"]
        want_location = (users.get(receiver) or {}).get("location", "")
        for listing in sorted(listings, key=lambda l: l["id"]):
            giver = listing["owner_id"]
            if giver == receiver:
                continue
            semantic = scores.get((listing["id"], want["id"])) if scores is not None else listing_want_semantic_score(listing, want)
            result = score_pair(listing, want, semantic, want_location=want_location, reserved=reserved, config=config)
            if not result.ok or result.score < config.edge_threshold:
                continue
            edge = {
                "from_user": giver,
                "to_user": receiver,
                "listing_id": listing["id"],
                "listing_title": listing["title"],
                "satisfies_want_id": want["id"],
                "want_title": want.get("title", ""),
                "value": round_money(listing["estimated_value"]),
                "currency": listing.get("currency", "USD"),
                "semantic_score": result.components["semantic"],
                "score": result.score,
                "components": result.components,
                "reasons": result.reasons,
            }
            key = (giver, receiver)
            current = best.get(key)
            if current is None or (-edge["score"], edge["listing_id"], edge["satisfies_want_id"]) < (
                -current["score"], current["listing_id"], current["satisfies_want_id"]
            ):
                best[key] = edge
    return best


def find_cycles(edges: Edges, max_len: int = 3, rejected: frozenset = frozenset()) -> List[List[str]]:
    """Bounded DFS. Returns node paths [a, b, (c)] meaning a->b->(c)->a, each rooted at its smallest id."""
    max_len = max(2, min(SUPPORTED_MAX_LEN, max_len))
    adjacency: Dict[str, List[str]] = {}
    for giver, receiver in edges:
        adjacency.setdefault(giver, []).append(receiver)
    for node in adjacency:
        adjacency[node].sort()

    found: List[List[str]] = []

    def dfs(start: str, node: str, path: List[str]) -> None:
        for nxt in adjacency.get(node, []):
            if nxt == start and len(path) >= 2:
                if cycle_is_valid(path, edges) and cycle_key(path) not in rejected:
                    found.append(list(path))
            elif nxt > start and nxt not in path and len(path) < max_len:
                dfs(start, nxt, path + [nxt])

    for start in sorted(adjacency):
        dfs(start, start, [start])
    return found


def cycle_key(path: Sequence[str]) -> str:
    """Stable id: size + path rotated to start at its smallest user id (direction-preserving)."""
    pivot = path.index(min(path))
    rotated = list(path[pivot:]) + list(path[:pivot])
    return f"c{len(path)}:" + ":".join(rotated)


def cycle_is_valid(path: Sequence[str], edges: Edges) -> bool:
    """Re-check the structural rules on a candidate path."""
    size = len(path)
    if size < 2 or len(set(path)) != size:
        return False  # repeated participant
    listings_used = []
    for index, giver in enumerate(path):
        receiver = path[(index + 1) % size]
        if giver == receiver or (giver, receiver) not in edges:
            return False  # self-exchange or missing compatibility edge
        listings_used.append(edges[(giver, receiver)]["listing_id"])
    return len(set(listings_used)) == size  # no duplicate listing


def assemble_cycle(path: Sequence[str], edges: Edges, users: Dict[str, dict]) -> Cycle:
    size = len(path)
    participants: List[CycleParticipant] = []
    edge_models: List[GraphEdge] = []
    for index, user_id in enumerate(path):
        out_edge = edges[(user_id, path[(index + 1) % size])]
        in_edge = edges[(path[(index - 1) % size], user_id)]
        given, received = round_money(out_edge["value"]), round_money(in_edge["value"])
        participants.append(
            CycleParticipant(
                user_id=user_id,
                user_name=(users.get(user_id) or {}).get("name", "Trader"),
                gives_listing_id=out_edge["listing_id"],
                gives_listing_title=out_edge["listing_title"],
                gives_value=given,
                receives_listing_id=in_edge["listing_id"],
                receives_listing_title=in_edge["listing_title"],
                receives_value=received,
                balance_amount=round_money(received - given),
                currency=out_edge["currency"],
                receives_via_want_id=in_edge["satisfies_want_id"],
                receives_via_want_title=in_edge["want_title"],
                incoming_edge_score=in_edge["score"],
            )
        )
        edge_models.append(GraphEdge(**{k: v for k, v in out_edge.items() if k != "reasons"}))

    scores = [edge.score for edge in edge_models]
    total_difference = round_money(sum(abs(p.balance_amount) for p in participants))
    key = cycle_key(path)
    names = {p.user_id: p.user_name for p in participants}
    reasons = [
        f"Every participant receives something from one of their own wants ({', '.join(p.receives_via_want_title or 'want' for p in participants)})",
        f"Weakest link scores {min(scores):.2f}; average edge score {sum(scores) / size:.2f}",
        "Values balance exactly" if total_difference == 0 else f"Value differences total {total_difference:.2f} {participants[0].currency}, settled by balancing payments if agreed",
    ]
    for edge in edge_models:
        reasons.append(f"{names.get(edge.from_user)} → {names.get(edge.to_user)}: {edge.listing_title} fills “{edge.want_title}” (score {edge.score:.2f})")
    return Cycle(
        key=key,
        id=key,
        cycle_type=size,
        participant_ids=list(path),
        participants=participants,
        total_value=round_money(sum(p.gives_value for p in participants)),
        total_imbalance=total_difference,
        mean_semantic_score=round(sum(e.semantic_score for e in edge_models) / size, 4),
        min_edge_score=round(min(scores), 4),
        avg_edge_score=round(sum(scores) / size, 4),
        reasons=reasons,
        edges=edge_models,
    )


def rank_cycles(cycles: List[Cycle]) -> List[Cycle]:
    ordered = sorted(
        cycles,
        key=lambda c: (-c.min_edge_score, -c.avg_edge_score, c.total_imbalance, c.cycle_type, c.key),
    )
    for index, cycle in enumerate(ordered, start=1):
        cycle.rank = index
    return ordered


def discover_from_inputs(
    listings: Sequence[dict],
    wants: Sequence[dict],
    users: Dict[str, dict],
    *,
    max_len: int = 3,
    scores: Optional[Dict[Tuple[str, str], float]] = None,
    reserved: frozenset = frozenset(),
    rejected: frozenset = frozenset(),
    config: Optional[ScoringConfig] = None,
) -> List[Cycle]:
    edges = build_edges(listings, wants, users, scores=scores, reserved=reserved, config=config)
    paths = find_cycles(edges, max_len=max_len, rejected=rejected)
    return rank_cycles([assemble_cycle(path, edges, users) for path in paths])


# ---------------------------------------------------------------- database-backed entry points

async def _load_inputs():
    reserved = frozenset(await reserved_listing_ids())
    listings = [l for l in await db.listings.find({"status": "active"}).to_list(MAX_LISTINGS_SCANNED) if l["id"] not in reserved]
    wants = await db.wants.find({"status": "open"}).to_list(MAX_WANTS_SCANNED)
    user_ids = list({l["owner_id"] for l in listings} | {w["user_id"] for w in wants})
    users = {u["id"]: u for u in await db.users.find({"id": {"$in": user_ids}}).to_list(len(user_ids) + 1)}
    rejected = frozenset(doc["cycle_key"] for doc in await db.cycle_rejections.find({}, {"cycle_key": 1}).to_list(5000))
    return listings, wants, users, reserved, rejected


async def discover_cycles(max_nodes: int = 3, limit: int = 20) -> List[Cycle]:
    listings, wants, users, reserved, rejected = await _load_inputs()
    scores = await pair_scores(listings, wants)
    cycles = discover_from_inputs(
        listings, wants, users, max_len=max_nodes, scores=scores, reserved=reserved, rejected=rejected
    )
    return cycles[:limit]


async def find_cycle(cycle_key_value: str) -> Optional[Cycle]:
    """Re-derive a cycle from current data (never trust a client-supplied cycle)."""
    size = 3 if cycle_key_value.startswith("c3:") else 2
    for cycle in await discover_cycles(max_nodes=size, limit=500):
        if cycle.key == cycle_key_value:
            return cycle
    return None


async def graph_stats() -> dict:
    listings, wants, users, reserved, rejected = await _load_inputs()
    scores = await pair_scores(listings, wants)
    edges = build_edges(listings, wants, users, scores=scores, reserved=reserved)
    paths = find_cycles(edges, max_len=3, rejected=rejected)
    return {
        "nodes": len({u for pair in edges for u in pair}),
        "edges": len(edges),
        "two_cycles": len([p for p in paths if len(p) == 2]),
        "three_cycles": len([p for p in paths if len(p) == 3]),
        "generated_at": utc_now(),
        "note": "Deterministic cycles are candidates only. Each one still needs every participant's approval.",
    }


async def cycles_payload(max_nodes: int = 3, limit: int = 20) -> dict:
    cycles = await discover_cycles(max_nodes=max_nodes, limit=limit)
    return {"cycles": cycles, "candidate_count": len(cycles), "generated_at": utc_now()}

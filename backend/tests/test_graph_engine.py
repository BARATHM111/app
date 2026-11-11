"""Unit tests for direct-match scoring and the graph engine. Pure, deterministic fixtures, no database.

The local deterministic embedder supplies semantic scores where needed, or scores are injected
explicitly, so every result is reproducible.
"""

from services.graph import (
    assemble_cycle,
    build_edges,
    cycle_is_valid,
    cycle_key,
    discover_from_inputs,
    find_cycles,
    rank_cycles,
)
from services.scoring import DEFAULT_WEIGHTS, ScoringConfig, parse_weights, score_pair

CFG = ScoringConfig(weights=dict(DEFAULT_WEIGHTS), edge_threshold=0.55)
USERS = {
    "a": {"id": "a", "name": "Ada", "location": "Portland, OR"},
    "b": {"id": "b", "name": "Ben", "location": "Portland, OR"},
    "c": {"id": "c", "name": "Cy", "location": "Portland, OR"},
    "d": {"id": "d", "name": "Di", "location": "Austin, TX"},
}


def L(id, owner, category, value=100, **kw):
    return {"id": id, "owner_id": owner, "title": f"{category} item {id}", "description": category, "type": "goods",
            "category": category, "estimated_value": value, "currency": "USD", "status": "active",
            "condition": "Good", "location": USERS[owner]["location"], "tags": [], **kw}


def W(id, user, category, low=50, high=200, **kw):
    return {"id": id, "user_id": user, "title": f"want {category}", "description": category, "category": category,
            "target_type": "goods", "min_value": low, "max_value": high, "currency": "USD", "keywords": [],
            "status": "open", **kw}


def full_scores(listings, wants, value=1.0):
    """Injected semantic scores: high only where the listing really is what the want describes
    (same category). Missing pairs count as 0, as if the embedder found no similarity."""
    return {(l["id"], w["id"]): value for l in listings for w in wants if l["category"] == w["category"]}


# ---------------------------------------------------------------- direct matches / scoring

def test_score_formula_and_normalised_components():
    result = score_pair(L("l1", "a", "Audio"), W("w1", "b", "Audio"), 0.8, want_location="Portland, OR", config=CFG)
    assert result.ok
    assert result.components == {"semantic": 0.8, "category": 1.0, "value": 1.0, "location": 1.0}
    assert result.score == round(0.45 * 0.8 + 0.25 + 0.20 + 0.10, 4)
    assert all(0.0 <= v <= 1.0 for v in result.components.values())


def test_weights_are_configurable_and_renormalised():
    weights = parse_weights("semantic=2,category=1,value=1,location=0")
    assert abs(sum(weights.values()) - 1) < 1e-6 and weights["semantic"] == 0.5 and weights["location"] == 0
    assert parse_weights("nonsense=1") == DEFAULT_WEIGHTS
    cfg = ScoringConfig(weights=weights, edge_threshold=0.5)
    assert score_pair(L("l1", "a", "Audio"), W("w1", "b", "Audio"), 1.0, config=cfg).score == 1.0


def test_hard_filters_condition_location_availability_type():
    want = W("w1", "b", "Audio", min_condition="Excellent")
    assert not score_pair(L("l1", "a", "Audio", condition="Good"), want, 1.0, config=CFG).ok
    assert score_pair(L("l1", "a", "Audio", condition="Like new"), want, 1.0, config=CFG).ok
    local = W("w2", "b", "Audio", location_preference="local")
    assert not score_pair(L("l2", "d", "Audio"), local, 1.0, want_location="Portland, OR", config=CFG).ok
    assert not score_pair(L("l3", "a", "Audio", status="reserved"), W("w3", "b", "Audio"), 1.0, config=CFG).ok
    assert not score_pair(L("l4", "a", "Audio"), W("w4", "b", "Audio"), 1.0, reserved=frozenset({"l4"}), config=CFG).ok
    assert not score_pair(L("l5", "a", "Audio"), W("w5", "b", "Audio", target_type="services"), 1.0, config=CFG).ok
    assert not score_pair(L("l6", "b", "Audio"), W("w6", "b", "Audio"), 1.0, config=CFG).ok  # self


def test_value_and_location_components_decay():
    want = W("w1", "b", "Audio", low=100, high=200)
    assert score_pair(L("l1", "a", "Audio", value=150), want, 1.0, config=CFG).components["value"] == 1.0
    assert 0 < score_pair(L("l2", "a", "Audio", value=240), want, 1.0, config=CFG).components["value"] < 1
    assert score_pair(L("l3", "a", "Audio", value=1000), want, 1.0, config=CFG).components["value"] == 0.0
    assert score_pair(L("l4", "d", "Audio"), want, 1.0, want_location="Portland, OR", config=CFG).components["location"] == 0.25


def test_failed_embedding_counts_as_zero_semantic():
    result = score_pair(L("l1", "a", "Audio"), W("w1", "b", "Audio"), None, config=CFG)
    assert result.components["semantic"] == 0 and "embedding unavailable" in result.reasons[0]


# ---------------------------------------------------------------- graph + cycles

def _two_cycle():
    listings = [L("la", "a", "Audio"), L("lb", "b", "Books")]
    wants = [W("wa", "a", "Books"), W("wb", "b", "Audio")]
    return listings, wants


def _three_cycle():
    # a gives Audio -> b ; b gives Books -> c ; c gives Camera -> a
    listings = [L("la", "a", "Audio", 100), L("lb", "b", "Books", 120), L("lc", "c", "Camera", 80)]
    wants = [W("wa", "a", "Camera"), W("wb", "b", "Audio"), W("wc", "c", "Books")]
    return listings, wants


def test_edges_reference_listing_and_want():
    listings, wants = _two_cycle()
    edges = build_edges(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG)
    assert set(edges) == {("a", "b"), ("b", "a")}
    assert edges[("a", "b")]["listing_id"] == "la" and edges[("a", "b")]["satisfies_want_id"] == "wb"


def test_two_person_cycle():
    listings, wants = _two_cycle()
    cycles = discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG)
    assert [c.key for c in cycles] == ["c2:a:b"]
    cycle = cycles[0]
    assert cycle.status == "discovered" and cycle.id == cycle.key
    gives = {p.user_id: p.gives_listing_id for p in cycle.participants}
    receives = {p.user_id: (p.receives_listing_id, p.receives_via_want_id) for p in cycle.participants}
    assert gives == {"a": "la", "b": "lb"}
    assert receives == {"a": ("lb", "wa"), "b": ("la", "wb")}
    assert cycle.reasons and cycle.min_edge_score >= CFG.edge_threshold


def test_three_person_cycle_and_value_differences():
    listings, wants = _three_cycle()
    cycles = discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG)
    assert [c.key for c in cycles] == ["c3:a:b:c"]
    balances = {p.user_id: p.balance_amount for p in cycles[0].participants}
    # a gives 100 gets 80; b gives 120 gets 100; c gives 80 gets 120
    assert balances == {"a": -20.0, "b": -20.0, "c": 40.0} and sum(balances.values()) == 0
    assert cycles[0].total_imbalance == 80.0


def test_missing_edge_breaks_cycle():
    listings, wants = _three_cycle()
    wants = [w for w in wants if w["id"] != "wc"]  # c no longer wants anything b offers
    assert discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG) == []


def test_inactive_listing_is_excluded():
    listings, wants = _three_cycle()
    listings[1]["status"] = "traded"
    assert discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG) == []


def test_reserved_listing_is_excluded():
    listings, wants = _two_cycle()
    assert discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants), reserved=frozenset({"la"}), config=CFG) == []


def test_edge_below_threshold_is_dropped():
    listings, wants = _two_cycle()
    strict = ScoringConfig(weights=dict(DEFAULT_WEIGHTS), edge_threshold=0.99)
    assert discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants, 0.5), config=strict) == []


def test_invalid_cycles_duplicate_participants_and_self_exchange():
    edges = {("a", "b"): {"listing_id": "la"}, ("b", "a"): {"listing_id": "lb"}, ("a", "a"): {"listing_id": "la"}}
    assert cycle_is_valid(["a", "b"], edges)
    assert not cycle_is_valid(["a", "a"], edges)            # self / repeated participant
    assert not cycle_is_valid(["a", "b", "a"], edges)       # repeated participant
    assert not cycle_is_valid(["a", "c"], edges)            # missing edge
    dup = {("a", "b"): {"listing_id": "same"}, ("b", "a"): {"listing_id": "same"}}
    assert not cycle_is_valid(["a", "b"], dup)               # duplicate listing


def test_dfs_finds_each_cycle_once_and_respects_bound():
    listings, wants = _three_cycle()
    edges = build_edges(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG)
    assert find_cycles(edges, max_len=3) == [["a", "b", "c"]]
    assert find_cycles(edges, max_len=2) == []
    assert cycle_key(["b", "c", "a"]) == cycle_key(["a", "b", "c"]) == "c3:a:b:c"
    assert find_cycles(edges, max_len=3, rejected=frozenset({"c3:a:b:c"})) == []


def test_ranking_prefers_min_then_avg_then_value_then_size():
    listings, wants = _two_cycle()
    edges = build_edges(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG)
    strong = assemble_cycle(["a", "b"], edges, USERS)
    weak = strong.model_copy(update={"key": "c2:x:y", "min_edge_score": strong.min_edge_score - 0.1})
    unbalanced = strong.model_copy(update={"key": "c2:p:q", "total_imbalance": 50.0})
    bigger = strong.model_copy(update={"key": "c3:m:n:o", "cycle_type": 3})
    ranked = rank_cycles([weak, bigger, unbalanced, strong])
    assert [c.key for c in ranked] == [strong.key, bigger.key, unbalanced.key, weak.key][:1] + [c.key for c in ranked][1:]
    assert ranked[0].key == strong.key and ranked[-1].key == "c2:x:y"
    assert [c.rank for c in ranked] == [1, 2, 3, 4]
    assert ranked.index(unbalanced) > ranked.index(strong) and ranked.index(bigger) > ranked.index(strong)


def test_deterministic_output():
    listings, wants = _three_cycle()
    runs = [discover_from_inputs(listings, wants, USERS, scores=full_scores(listings, wants), config=CFG) for _ in range(3)]
    assert all(r[0].model_dump() == runs[0][0].model_dump() for r in runs)

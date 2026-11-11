"""Unit tests for the deterministic core: compatibility, value maths, embeddings, cycle assembly."""

from services.compatibility import check_compatibility, round_money, value_closeness
from lib.embeddings import cosine_similarity, embed_text


def _listing(**overrides):
    base = {
        "id": "l1",
        "owner_id": "a",
        "title": "Walnut desk",
        "description": "handmade walnut desk",
        "type": "goods",
        "category": "Furniture",
        "currency": "USD",
        "estimated_value": 450.0,
        "status": "active",
        "tags": ["desk"],
    }
    base.update(overrides)
    return base


def _want(**overrides):
    base = {
        "id": "w1",
        "user_id": "b",
        "title": "wooden desk",
        "description": "a walnut desk",
        "category": "Furniture",
        "target_type": "goods",
        "currency": "USD",
        "min_value": 400.0,
        "max_value": 600.0,
        "keywords": ["desk"],
    }
    base.update(overrides)
    return base


def test_compatible_listing_passes():
    result = check_compatibility(_listing(), _want())
    assert result.ok
    assert result.blockers == []


def test_type_mismatch_blocks():
    assert not check_compatibility(_listing(type="services"), _want()).ok


def test_category_mismatch_blocks():
    assert not check_compatibility(_listing(category="Audio"), _want()).ok


def test_currency_mismatch_blocks():
    assert not check_compatibility(_listing(currency="EUR"), _want()).ok


def test_value_outside_range_blocks():
    assert not check_compatibility(_listing(estimated_value=900), _want()).ok


def test_own_listing_blocks():
    assert not check_compatibility(_listing(owner_id="b"), _want()).ok


def test_inactive_listing_blocks():
    assert not check_compatibility(_listing(status="reserved"), _want()).ok


def test_any_target_type_accepts_services():
    assert check_compatibility(_listing(type="services"), _want(target_type="any")).ok


def test_value_closeness_and_rounding():
    assert value_closeness(100, 100) == 1.0
    assert value_closeness(100, 50) == 0.5
    assert value_closeness(0, 0) == 1.0
    assert round_money(0.1 + 0.2) == 0.3


def test_embeddings_are_deterministic_and_normalised():
    a = embed_text("vintage 35mm rangefinder camera")
    b = embed_text("vintage 35mm rangefinder camera")
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-9
    related = cosine_similarity(a, embed_text("35mm camera rangefinder lens"))
    unrelated = cosine_similarity(a, embed_text("legal contract redlining service"))
    assert related > unrelated


def test_embedding_of_empty_text_is_zero_vector():
    assert cosine_similarity(embed_text(""), embed_text("camera")) == 0.0

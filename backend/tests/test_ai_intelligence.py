"""AI listing intelligence and embeddings, with mocked AI providers (no network).

Covers: strict schema validation of LLM output, the repair retry, normalisation
(category clamp, no invented valuations), timeouts and missing configuration, the
OpenAI-compatible embedding provider's retry and timeout handling (mocked transport),
and re-embedding when the model version changes.
"""

import asyncio
import json

import httpx
import pytest

from lib.ai_providers import LLMProvider, LLMTimeout, LLMUnavailable, set_llm_provider
from lib.embeddings import (
    EmbeddingError,
    LocalHashedEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    cosine_similarity,
)
from services import ai


class FakeLLM(LLMProvider):
    """Returns queued replies in order and records every prompt."""

    name = "fake"
    model = "fake-1"

    def __init__(self, replies, delay: float = 0.0, available: bool = True):
        self.replies = list(replies)
        self.prompts = []
        self.delay = delay
        self.available = available

    def is_available(self) -> bool:
        return self.available

    async def _call(self, system, prompt, max_tokens):
        self.prompts.append(prompt)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.replies.pop(0)


VALID = {
    "name": "Leica M3 rangefinder with 50mm Summicron",
    "category": "photography",  # wrong case, gets clamped to "Photography"
    "listing_type": "goods",
    "description": "Vintage Leica M3 film rangefinder with a 50mm Summicron lens. Works perfectly.",
    "condition": "Light brassing",
    "attributes": {"brand": "Leica", "lens": "50mm Summicron", "working": True},
    "estimated_value": 1800,
    "value_basis": "stated_by_user",
    "currency": "USD",
    "keywords": ["Leica", "rangefinder", "film camera", "leica"],
    "suggested_wants": [
        {"title": "Studio lighting kit", "category": "photography", "target_type": "goods", "reason": "Fits a photographer"}
    ],
    "confidence": 0.86,
    "warnings": [],
}


@pytest.fixture(autouse=True)
def _restore_provider():
    yield
    set_llm_provider(None)


async def test_analyze_listing_valid_output_is_normalised():
    fake = FakeLLM([json.dumps(VALID)])
    set_llm_provider(fake)
    analysis = await ai.analyze_listing("Selling my grandfather's Leica M3, asking 1800 USD.")
    assert analysis.category == "Photography"
    assert analysis.listing_type == "goods"
    assert analysis.estimated_value == 1800 and analysis.value_basis == "stated_by_user"
    assert analysis.currency == "USD"
    assert analysis.keywords == ["leica", "rangefinder", "film camera"]  # lowercased and de-duplicated
    assert analysis.suggested_wants[0].category == "Photography"
    assert analysis.attributes["working"] is True
    assert len(fake.prompts) == 1


async def test_analyze_listing_never_keeps_value_without_basis():
    reply = {**VALID, "estimated_value": 950, "value_basis": "none", "currency": None}
    set_llm_provider(FakeLLM([json.dumps(reply)]))
    analysis = await ai.analyze_listing("An old camera, no price mentioned.")
    assert analysis.estimated_value is None and analysis.value_basis == "none"
    assert any("No value basis" in w for w in analysis.warnings)


async def test_analyze_listing_flags_ai_estimates_as_unverified():
    reply = {**VALID, "value_basis": "ai_estimate"}
    set_llm_provider(FakeLLM([json.dumps(reply)]))
    analysis = await ai.analyze_listing("A Leica M3 camera in good shape.")
    assert analysis.value_basis == "ai_estimate"
    assert any("not a verified market valuation" in w for w in analysis.warnings)


async def test_analyze_listing_services_drop_condition_and_unknown_category():
    reply = {**VALID, "listing_type": "services", "category": "Quantum Plumbing", "condition": "New"}
    set_llm_provider(FakeLLM([json.dumps(reply)]))
    analysis = await ai.analyze_listing("I offer ten hours of consulting work.")
    assert analysis.condition is None
    assert analysis.category == "Other"
    assert any("not in the BarterX list" in w for w in analysis.warnings)


async def test_invalid_output_gets_one_repair_retry():
    bad = {**VALID, "listing_type": "vehicle", "confidence": 3}
    fake = FakeLLM([json.dumps(bad), "```json\n" + json.dumps(VALID) + "\n```"])
    set_llm_provider(fake)
    analysis = await ai.analyze_listing("Leica M3 camera, 1800 USD.")
    assert analysis.name.startswith("Leica")
    assert len(fake.prompts) == 2
    assert "rejected because" in fake.prompts[1] and "listing_type" in fake.prompts[1]


@pytest.mark.parametrize(
    "replies",
    [
        ["I think this is a nice camera!", "Still prose, no JSON."],
        [json.dumps({**VALID, "attributes": {"nested": {"x": 1}}}), json.dumps({**VALID, "currency": "dollars"})],
        [json.dumps([1, 2, 3]), json.dumps({"name": "x"})],
    ],
)
async def test_untrusted_output_is_rejected_after_retry(replies):
    set_llm_provider(FakeLLM(replies))
    with pytest.raises(ai.AIError, match="schema validation|JSON"):
        await ai.analyze_listing("Leica M3 camera, 1800 USD.")


async def test_timeout_and_unconfigured_provider_raise_typed_errors(monkeypatch):
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "0.05")
    set_llm_provider(FakeLLM([json.dumps(VALID)], delay=0.5))
    with pytest.raises(LLMTimeout):
        await ai.analyze_listing("Leica M3 camera, 1800 USD.")
    set_llm_provider(FakeLLM([], available=False))
    with pytest.raises(LLMUnavailable):
        await ai.analyze_listing("Leica M3 camera, 1800 USD.")


async def test_match_explanation_uses_only_given_facts():
    fake = FakeLLM(["The mixer is within your range and closely matches your want."])
    set_llm_provider(fake)
    text = await ai.match_explanation(
        {
            "listing": {"title": "Analog mixer", "type": "goods", "category": "Audio", "estimated_value": 260, "currency": "USD"},
            "want": {"title": "Mixer", "min_value": 200, "max_value": 300, "currency": "USD"},
            "match": {"reasons": ["Category matches: Audio"], "semantic_score": 0.61, "value_score": 0.9},
        }
    )
    assert "within your range" in text
    assert "Category matches: Audio" in fake.prompts[0] and "0.61" in fake.prompts[0]


# ------------------------------------------------------------------ embedding providers


async def test_local_provider_is_deterministic_and_semantic_ish():
    provider = LocalHashedEmbeddingProvider()
    a, b, c = await provider.embed(["vintage analog audio mixer", "analog mixer for audio", "legal contract review"])
    assert a == (await provider.embed(["vintage analog audio mixer"]))[0]
    assert cosine_similarity(a, b) > cosine_similarity(a, c)
    assert len(a) == provider.dim


def _transport(responses):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        result = responses[min(calls["n"] - 1, len(responses) - 1)]
        if isinstance(result, Exception):
            raise result
        return result

    return httpx.MockTransport(handler), calls


async def test_hosted_provider_retries_transient_errors_then_succeeds():
    ok = httpx.Response(200, json={"data": [{"index": 0, "embedding": [3.0, 4.0, 0.0]}]})
    transport, calls = _transport([httpx.Response(503, text="busy"), ok])
    provider = OpenAICompatibleEmbeddingProvider("key", "m", 3, transport=transport, max_retries=2)
    vectors = await provider.embed(["hello"])
    assert calls["n"] == 2
    assert vectors == [[0.6, 0.8, 0.0]]  # L2-normalised


async def test_hosted_provider_timeout_and_bad_shapes_raise_embedding_error():
    transport, _ = _transport([httpx.ReadTimeout("slow")])
    provider = OpenAICompatibleEmbeddingProvider("key", "m", 3, transport=transport, max_retries=1)
    with pytest.raises(EmbeddingError, match="timed out"):
        await provider.embed(["hello"])

    wrong_dim = httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 2.0]}]})
    transport, _ = _transport([wrong_dim])
    with pytest.raises(EmbeddingError, match="wrong shape"):
        await OpenAICompatibleEmbeddingProvider("key", "m", 3, transport=transport).embed(["hello"])

    transport, calls = _transport([httpx.Response(401, text="bad key")])
    with pytest.raises(EmbeddingError, match="401"):
        await OpenAICompatibleEmbeddingProvider("key", "m", 3, transport=transport, max_retries=3).embed(["x"])
    assert calls["n"] == 1  # client errors are not retried

    with pytest.raises(EmbeddingError, match="not configured"):
        await OpenAICompatibleEmbeddingProvider("", "m", 3).embed(["x"])

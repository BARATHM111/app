"""Embedding provider abstraction.

`EmbeddingProvider.embed(texts)` is the only thing business logic depends on.
Each provider exposes `model` and `version`; stored vectors carry both, so a
change of model or version marks every stored vector stale and `reembed` fixes it.

Providers:
- `local`  — deterministic hashed bag-of-words + bigrams (no network, reproducible).
            Default here because the managed key exposes no embedding model.
- `openai` — any OpenAI-compatible `/v1/embeddings` endpoint (OpenAI, Azure-compatible
            gateways, etc.), configured by EMBEDDING_API_BASE / EMBEDDING_API_KEY /
            EMBEDDING_MODEL / EMBEDDING_DIM. Bounded by a timeout with retries on 429/5xx.

Similarity is cosine similarity; this layer only ranks *candidates* that the
deterministic compatibility rules have already accepted.
"""

import asyncio
import hashlib
import math
import os
import re
from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

LOCAL_DIM = 256
LOCAL_MODEL = "local-hashed-bow"
LOCAL_VERSION = "1"

# Back-compat names used by the compatibility module and unit tests.
EMBEDDING_DIM = LOCAL_DIM
EMBEDDING_MODEL = f"{LOCAL_MODEL}-v{LOCAL_VERSION}"

_STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "with", "is", "are",
    "am", "be", "by", "at", "as", "it", "its", "this", "that", "my", "your", "our",
    "i", "we", "you", "they", "want", "wants", "wanted", "looking", "look", "trade",
    "exchange", "barter", "would", "like", "some", "any", "very", "good", "new",
    "used", "offer", "offering", "give", "giving", "get", "can", "will", "from",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingError(RuntimeError):
    """The embedding provider failed, timed out or returned malformed vectors."""


class EmbeddingProvider(ABC):
    name: str = "abstract"
    model: str = ""
    version: str = "1"
    dim: int = 0

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[List[float]]: ...

    def describe(self) -> dict:
        return {"provider": self.name, "model": self.model, "version": self.version, "dim": self.dim}


# ---------------------------------------------------------------- local provider


def _tokens(text: str) -> list[str]:
    words = [w for w in _TOKEN_RE.findall((text or "").lower()) if w not in _STOPWORDS and len(w) > 1]
    bigrams = [f"{a}_{b}" for a, b in zip(words, words[1:])]
    return words + bigrams


def _bucket(token: str) -> int:
    # blake2b, not hash(): Python's built-in hash is salted per process.
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % LOCAL_DIM


def embed_text(text: str) -> list[float]:
    """Deterministic unit-length local embedding of `text` (sync helper)."""
    vector = [0.0] * LOCAL_DIM
    tokens = _tokens(text)
    if not tokens:
        return vector
    counts: dict[int, int] = {}
    for token in tokens:
        bucket = _bucket(token)
        counts[bucket] = counts.get(bucket, 0) + 1
    for bucket, count in counts.items():
        vector[bucket] = 1.0 + math.log(count)  # sublinear weighting
    return normalise(vector)


class LocalHashedEmbeddingProvider(EmbeddingProvider):
    name = "local"
    model = LOCAL_MODEL
    version = LOCAL_VERSION
    dim = LOCAL_DIM

    async def embed(self, texts: List[str]) -> List[List[float]]:
        return [embed_text(text) for text in texts]


# ---------------------------------------------------------------- hosted provider


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str,
        dim: int,
        version: str = "1",
        api_base: str = "https://api.openai.com/v1",
        timeout: float = 20.0,
        max_retries: int = 2,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self.version = version
        self.api_base = api_base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport  # injectable for tests

    async def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            raise EmbeddingError("EMBEDDING_API_KEY is not configured on the backend")
        payload = {"model": self.model, "input": texts}
        if self.dim:
            payload["dimensions"] = self.dim
        last_error = "unknown error"
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self._transport) as client:
                    response = await client.post(
                        f"{self.api_base}/embeddings",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
            except httpx.TimeoutException:
                last_error = f"embedding request timed out after {self.timeout:.0f}s"
            except httpx.HTTPError as exc:
                last_error = f"embedding transport error: {exc}"
            else:
                if response.status_code == 200:
                    return self._parse(response.json(), len(texts))
                last_error = f"embedding API returned {response.status_code}: {response.text[:200]}"
                if response.status_code not in (429, 500, 502, 503, 504):
                    break  # client errors are not retried
            if attempt < self.max_retries:
                await asyncio.sleep(0.5 * (2**attempt))
        raise EmbeddingError(last_error)

    def _parse(self, data: dict, expected: int) -> List[List[float]]:
        rows = sorted(data.get("data") or [], key=lambda row: row.get("index", 0))
        if len(rows) != expected:
            raise EmbeddingError(f"expected {expected} vectors, got {len(rows)}")
        vectors = []
        for row in rows:
            vector = row.get("embedding")
            if not isinstance(vector, list) or (self.dim and len(vector) != self.dim):
                raise EmbeddingError("embedding API returned a vector with the wrong shape")
            vectors.append(normalise([float(x) for x in vector]))
        return vectors


# ---------------------------------------------------------------- shared maths


def normalise(vector: List[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity clamped to [0, 1] (vectors are stored L2-normalised)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def listing_text(title: str, description: str = "", category: str = "", tags: list[str] | None = None) -> str:
    parts = [title or "", description or "", category or "", " ".join(tags or [])]
    return " ".join(part for part in parts if part)


def want_text(title: str, description: str = "", category: str = "", keywords: list[str] | None = None) -> str:
    parts = [title or "", description or "", category or "", " ".join(keywords or [])]
    return " ".join(part for part in parts if part)


def source_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- configuration


def build_embedding_provider() -> EmbeddingProvider:
    name = os.environ.get("EMBEDDING_PROVIDER", "local").lower()
    if name == "openai":
        return OpenAICompatibleEmbeddingProvider(
            api_key=os.environ.get("EMBEDDING_API_KEY", ""),
            model=os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            dim=int(os.environ.get("EMBEDDING_DIM", "1536")),
            version=os.environ.get("EMBEDDING_VERSION", "1"),
            api_base=os.environ.get("EMBEDDING_API_BASE", "https://api.openai.com/v1"),
            timeout=float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "20")),
        )
    provider = LocalHashedEmbeddingProvider()
    provider.version = os.environ.get("EMBEDDING_VERSION", LOCAL_VERSION)
    return provider


_override: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    return _override or build_embedding_provider()


def set_embedding_provider(provider: Optional[EmbeddingProvider]) -> None:
    """Test hook: install a fake provider (None restores the configured one)."""
    global _override
    _override = provider


def provider_name() -> str:
    return get_embedding_provider().name

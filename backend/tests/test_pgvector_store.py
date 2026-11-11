"""PgVectorEmbeddingStore against a real PostgreSQL + pgvector database.

Runs only when PGVECTOR_TEST_URL points at a database where /app/prisma/migrations
has been applied (e.g. a Neon dev branch, or local Postgres 15 + pgvector 0.8.0).
Otherwise the tests are skipped, never faked.
"""

import os
import uuid

import pytest

from lib.embeddings import LocalHashedEmbeddingProvider
from services.embedding_store import EmbeddingRecord, PgVectorEmbeddingStore

DSN = os.environ.get("PGVECTOR_TEST_URL")
pytestmark = pytest.mark.skipif(not DSN, reason="PGVECTOR_TEST_URL not set; pgvector store tests need a real database")


def _record(kind, subject_id, owner, vector, model="local-hashed-bow", version="1", digest="h"):
    return EmbeddingRecord(kind, subject_id, owner, "local", model, version, len(vector), digest, vector)


@pytest.fixture
async def store():
    s = PgVectorEmbeddingStore(DSN)
    pool = await s._conn()
    await pool.execute("DELETE FROM embeddings WHERE subject_id LIKE 'pgt-%'")
    yield s
    await pool.execute("DELETE FROM embeddings WHERE subject_id LIKE 'pgt-%'")
    await s.close()


async def test_upsert_get_nearest_and_version_isolation(store):
    provider = LocalHashedEmbeddingProvider()
    texts = {
        "pgt-mixer": "vintage analog audio mixer twelve channels",
        "pgt-speakers": "studio monitor speakers for audio mixing",
        "pgt-legal": "contract review and legal redlining service",
    }
    vectors = dict(zip(texts, await provider.embed(list(texts.values()))))
    for subject_id, vector in vectors.items():
        await store.upsert(_record("listing", subject_id, f"owner-{subject_id}", vector))
    # Stale row (old model version) must never be returned by current-version queries.
    await store.upsert(_record("listing", "pgt-stale", "owner-x", vectors["pgt-mixer"], version="0"))
    # Upsert is idempotent per subject.
    await store.upsert(_record("listing", "pgt-mixer", "owner-pgt-mixer", vectors["pgt-mixer"], digest="h2"))

    query = (await provider.embed(["looking for an analog audio mixer"]))[0]
    neighbours = await store.nearest("listing", query, "local-hashed-bow", "1", 10)
    ids = [n.subject_id for n in neighbours if n.subject_id.startswith("pgt-")]
    assert ids[0] == "pgt-mixer"
    assert "pgt-stale" not in ids
    assert neighbours[0].score > neighbours[-1].score

    excluded = await store.nearest("listing", query, "local-hashed-bow", "1", 10, exclude_owner="owner-pgt-mixer")
    assert "pgt-mixer" not in [n.subject_id for n in excluded]

    got = await store.get_many("listing", ["pgt-mixer", "pgt-stale"], "local-hashed-bow", "1")
    assert set(got) == {"pgt-mixer"} and got["pgt-mixer"].source_hash == "h2"
    assert len(got["pgt-mixer"].vector) == 256

    hashes = await store.current_hashes("listing", "local-hashed-bow", "1")
    assert hashes["pgt-mixer"] == "h2" and "pgt-stale" not in hashes

    await store.delete("listing", "pgt-legal")
    assert "pgt-legal" not in await store.get_many("listing", ["pgt-legal"], "local-hashed-bow", "1")


async def test_hnsw_index_is_used_for_cosine_search(store):
    provider = LocalHashedEmbeddingProvider()
    for i in range(40):
        vector = (await provider.embed([f"item number {i} {uuid.uuid4().hex}"]))[0]
        await store.upsert(_record("listing", f"pgt-bulk-{i}", "owner-bulk", vector))
    pool = await store._conn()
    async with pool.acquire() as conn:
        await conn.execute("SET enable_seqscan = off")
        plan = await conn.fetch(
            """EXPLAIN SELECT subject_id FROM embeddings
               WHERE model = 'local-hashed-bow' AND version = '1' AND subject_kind = 'listing'
               ORDER BY (vector::vector(256)) <=> (SELECT vector::vector(256) FROM embeddings WHERE subject_id = 'pgt-bulk-0')
               LIMIT 5"""
        )
    text = "\n".join(row[0] for row in plan)
    assert "embeddings_hnsw_local_hashed_bow_v1" in text, text


async def test_dimension_check_constraint_rejects_mismatched_vectors(store):
    import asyncpg

    record = _record("listing", "pgt-bad", "o", [0.1, 0.2, 0.3])
    record.dim = 4  # claims 4 dimensions but carries 3
    with pytest.raises(asyncpg.CheckViolationError):
        await store.upsert(record)

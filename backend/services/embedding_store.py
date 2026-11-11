"""Vector storage behind one interface.

- `MongoEmbeddingStore` — what the preview runs on (in-pod MongoDB). Cosine retrieval
  is a brute-force scan over vectors of the *current* model+version, fine for MVP scale.
- `PgVectorEmbeddingStore` — PostgreSQL + pgvector (the Neon target). Uses the
  `embeddings` table from /app/prisma/migrations; retrieval is an HNSW cosine
  index scan (`ORDER BY (vector::vector(dim)) <=> $1`).

Selected by EMBEDDING_STORE=mongo|pgvector (pgvector needs PGVECTOR_DATABASE_URL).
Every record carries provider, model, version, dim and a hash of the source text, so
re-embedding only touches rows whose model/version/text changed.
"""

import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from lib.dates import utc_now
from lib.embeddings import cosine_similarity


@dataclass
class EmbeddingRecord:
    subject_kind: str  # "listing" | "want"
    subject_id: str
    owner_id: str
    provider: str
    model: str
    version: str
    dim: int
    source_hash: str
    vector: List[float]


@dataclass
class Neighbour:
    subject_id: str
    owner_id: str
    score: float


class EmbeddingStore(ABC):
    name = "abstract"

    @abstractmethod
    async def upsert(self, record: EmbeddingRecord) -> None: ...

    @abstractmethod
    async def get_many(self, kind: str, ids: Sequence[str], model: str, version: str) -> Dict[str, EmbeddingRecord]: ...

    @abstractmethod
    async def nearest(
        self, kind: str, vector: List[float], model: str, version: str, limit: int, exclude_owner: Optional[str] = None
    ) -> List[Neighbour]: ...

    @abstractmethod
    async def current_hashes(self, kind: str, model: str, version: str) -> Dict[str, str]: ...

    @abstractmethod
    async def delete(self, kind: str, subject_id: str) -> None: ...

    @abstractmethod
    async def counts(self, model: str, version: str) -> Dict[str, int]: ...


# ------------------------------------------------------------------- MongoDB


class MongoEmbeddingStore(EmbeddingStore):
    name = "mongo"

    def __init__(self, database=None):
        if database is None:
            from lib.db import db as database
        self.collection = database.embeddings

    async def upsert(self, record: EmbeddingRecord) -> None:
        now = utc_now()
        await self.collection.update_one(
            {"subject_kind": record.subject_kind, "subject_id": record.subject_id},
            {
                "$set": {
                    "id": f"emb_{record.subject_kind}_{record.subject_id}",
                    **record.__dict__,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def get_many(self, kind, ids, model, version):
        if not ids:
            return {}
        rows = await self.collection.find(
            {"subject_kind": kind, "subject_id": {"$in": list(ids)}, "model": model, "version": version}
        ).to_list(len(ids))
        return {row["subject_id"]: _record(row) for row in rows}

    async def nearest(self, kind, vector, model, version, limit, exclude_owner=None):
        query: dict = {"subject_kind": kind, "model": model, "version": version}
        if exclude_owner:
            query["owner_id"] = {"$ne": exclude_owner}
        scored = []
        async for row in self.collection.find(query, {"subject_id": 1, "owner_id": 1, "vector": 1}):
            scored.append(Neighbour(row["subject_id"], row["owner_id"], round(cosine_similarity(vector, row["vector"]), 4)))
        scored.sort(key=lambda n: (-n.score, n.subject_id))
        return scored[:limit]

    async def current_hashes(self, kind, model, version):
        rows = self.collection.find(
            {"subject_kind": kind, "model": model, "version": version}, {"subject_id": 1, "source_hash": 1}
        )
        return {row["subject_id"]: row["source_hash"] async for row in rows}

    async def delete(self, kind, subject_id):
        await self.collection.delete_many({"subject_kind": kind, "subject_id": subject_id})

    async def counts(self, model, version):
        total = await self.collection.count_documents({})
        current = await self.collection.count_documents({"model": model, "version": version})
        return {"total": total, "current": current, "stale": total - current}


def _record(row: dict) -> EmbeddingRecord:
    return EmbeddingRecord(
        subject_kind=row["subject_kind"],
        subject_id=row["subject_id"],
        owner_id=row.get("owner_id", ""),
        provider=row.get("provider", ""),
        model=row["model"],
        version=str(row["version"]),
        dim=int(row.get("dim") or len(row["vector"])),
        source_hash=row.get("source_hash", ""),
        vector=list(row["vector"]),
    )


# ------------------------------------------------------------------- pgvector


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vector) + "]"


_SAFE_IDENT = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


class PgVectorEmbeddingStore(EmbeddingStore):
    """asyncpg-backed store for PostgreSQL + pgvector (Neon in production).

    Vectors are written as text literals cast to `vector`, so no client-side codec is
    required. Table: see docs/prisma/migrations/0001_init/migration.sql.
    """

    name = "pgvector"

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool = None

    async def _conn(self):
        import asyncpg

        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4, command_timeout=15)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def upsert(self, record: EmbeddingRecord) -> None:
        pool = await self._conn()
        await pool.execute(
            """
            INSERT INTO embeddings (subject_kind, subject_id, owner_id, provider, model, version, dim,
                                    source_hash, vector, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, now(), now())
            ON CONFLICT (subject_kind, subject_id) DO UPDATE SET
              owner_id = EXCLUDED.owner_id, provider = EXCLUDED.provider, model = EXCLUDED.model,
              version = EXCLUDED.version, dim = EXCLUDED.dim, source_hash = EXCLUDED.source_hash,
              vector = EXCLUDED.vector, updated_at = now()
            """,
            record.subject_kind,
            record.subject_id,
            record.owner_id,
            record.provider,
            record.model,
            record.version,
            record.dim,
            record.source_hash,
            _vector_literal(record.vector),
        )

    async def get_many(self, kind, ids, model, version):
        if not ids:
            return {}
        pool = await self._conn()
        rows = await pool.fetch(
            """SELECT subject_kind, subject_id, owner_id, provider, model, version, dim, source_hash,
                      vector::text AS vector
               FROM embeddings WHERE subject_kind = $1 AND subject_id = ANY($2::text[])
                 AND model = $3 AND version = $4""",
            kind,
            list(ids),
            model,
            version,
        )
        return {row["subject_id"]: _record({**dict(row), "vector": json.loads(row["vector"])}) for row in rows}

    async def nearest(self, kind, vector, model, version, limit, exclude_owner=None):
        """Cosine top-k. The ORDER BY repeats the HNSW index expression `(vector::vector(dim))`
        and the partial-index predicate (literal model/version) so the planner can use the index.
        Model and version come from server config and are checked against a strict pattern
        before inlining. dim is an int."""
        if not (_SAFE_IDENT.match(model) and _SAFE_IDENT.match(version)):
            raise ValueError("embedding model/version contain unsupported characters")
        dim = int(len(vector))
        pool = await self._conn()
        rows = await pool.fetch(
            f"""SELECT subject_id, owner_id, 1 - ((vector::vector({dim})) <=> $1::vector({dim})) AS score
               FROM embeddings
               WHERE model = '{model}' AND version = '{version}'
                 AND subject_kind = $2 AND ($3::text IS NULL OR owner_id <> $3)
               ORDER BY (vector::vector({dim})) <=> $1::vector({dim})
               LIMIT $4""",
            _vector_literal(vector),
            kind,
            exclude_owner,
            limit,
        )
        rows = sorted(rows, key=lambda row: (-float(row["score"]), row["subject_id"]))  # deterministic ties
        return [
            Neighbour(row["subject_id"], row["owner_id"], round(max(0.0, min(1.0, float(row["score"]))), 4))
            for row in rows
        ]

    async def current_hashes(self, kind, model, version):
        pool = await self._conn()
        rows = await pool.fetch(
            "SELECT subject_id, source_hash FROM embeddings WHERE subject_kind = $1 AND model = $2 AND version = $3",
            kind,
            model,
            version,
        )
        return {row["subject_id"]: row["source_hash"] for row in rows}

    async def delete(self, kind, subject_id):
        pool = await self._conn()
        await pool.execute("DELETE FROM embeddings WHERE subject_kind = $1 AND subject_id = $2", kind, subject_id)

    async def counts(self, model, version):
        pool = await self._conn()
        total = await pool.fetchval("SELECT count(*) FROM embeddings")
        current = await pool.fetchval("SELECT count(*) FROM embeddings WHERE model = $1 AND version = $2", model, version)
        return {"total": int(total), "current": int(current), "stale": int(total) - int(current)}


# ------------------------------------------------------------------- selection

_store: Optional[EmbeddingStore] = None


def get_embedding_store() -> EmbeddingStore:
    global _store
    if _store is None:
        if os.environ.get("EMBEDDING_STORE", "mongo").lower() == "pgvector":
            _store = PgVectorEmbeddingStore(os.environ["PGVECTOR_DATABASE_URL"])
        else:
            _store = MongoEmbeddingStore()
    return _store


def set_embedding_store(store: Optional[EmbeddingStore]) -> None:
    """Test hook."""
    global _store
    _store = store

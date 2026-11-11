-- 0002: pgvector indexes and integrity rules that Prisma's schema language cannot express.
-- Verified against PostgreSQL 15 + pgvector 0.8.0 (Neon ships 0.8.0 for PG 14-17).

-- Rows written by the backend's pgvector store let the database assign the id.
ALTER TABLE "embeddings" ALTER COLUMN "id" SET DEFAULT gen_random_uuid();

-- The stored vector must have the dimension the row claims, and only listing or want subjects are allowed.
ALTER TABLE "embeddings"
  ADD CONSTRAINT "embeddings_dim_matches_vector" CHECK (vector_dims("vector") = "dim"),
  ADD CONSTRAINT "embeddings_subject_kind_valid" CHECK ("subject_kind" IN ('listing', 'want'));

-- HNSW cosine indexes, one per (model, version, dimension). HNSW needs a fixed dimension,
-- so each index casts to that dimension and is restricted to that model's rows. A new
-- embedding model gets its own index in a new migration, and old rows stay queryable
-- until re-embedding replaces them.
CREATE INDEX "embeddings_hnsw_local_hashed_bow_v1"
  ON "embeddings" USING hnsw (("vector"::vector(256)) vector_cosine_ops)
  WHERE "model" = 'local-hashed-bow' AND "version" = '1';

CREATE INDEX "embeddings_hnsw_text_embedding_3_small_v1"
  ON "embeddings" USING hnsw (("vector"::vector(1536)) vector_cosine_ops)
  WHERE "model" = 'text-embedding-3-small' AND "version" = '1';

-- A listing can be given in only one active (non-terminal) exchange at a time.
CREATE UNIQUE INDEX "one_active_exchange_per_listing"
  ON "ExchangeParticipant" ("givesListingId") WHERE "active";

-- Each author gets one unverified review per subject. Verified reviews are unique per exchange via @@unique.
CREATE UNIQUE INDEX "one_unverified_review_per_subject"
  ON "Review" ("authorId", "subjectId") WHERE "exchangeId" IS NULL;

ALTER TABLE "Review" ADD CONSTRAINT "review_rating_range" CHECK ("rating" BETWEEN 1 AND 5);
ALTER TABLE "Review" ADD CONSTRAINT "review_not_self" CHECK ("authorId" <> "subjectId");

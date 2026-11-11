# 07 — AI Integration Design

## Responsibilities
| Task | Engine | Output | Can change state? |
|---|---|---|---|
| Listing extraction | LLM (Claude Sonnet 4.6 via Emergent universal key) | JSON draft: title, type, category, condition, estimated value, tags, attributes, confidence, warnings | No. Shown for review; nothing is saved until the user publishes |
| Categorisation | LLM | 1–3 categories from a fixed vocabulary | No |
| Match explanation | LLM, given **only deterministic facts** (reasons, scores, values) | 2–3 sentences, cached on the Match | No |
| Deal summary and negotiation suggestions | LLM | summary, open questions, ideas | No |
| Semantic similarity | Embeddings | cosine score in [0,1] | No. It only ranks candidates that already passed compatibility checks |

## Guard rails
- `services/ai.py` has no access to exchange or payment mutation, and no route lets AI output approve, accept or pay.
- LLM output is parsed as JSON and then **re-validated** in Pydantic: the type is coerced to goods/services, the category is clamped to the vocabulary, value ≥ 0, confidence in [0,1]. A zero value adds a warning.
- Failures surface as 502/503 with the real error. The API never substitutes invented content.
- The prompts instruct the model not to invent facts and to call values estimates. The UI shows a disclaimer on every AI surface.

## Embeddings: deviation from the target
The managed universal key in this environment exposes **chat models only**. Embedding model IDs returned "invalid model" from the proxy. To keep matching real and testable instead of faked, embeddings use a **deterministic local provider** (`lib/embeddings.py`): a hashed bag-of-words plus bigrams, 256 dimensions, L2-normalised, with blake2b hashing so results are identical across processes. It is reproducible, needs no network, and is unit-tested.

**Target**: an `EmbeddingProvider` interface with a hosted model (e.g. `text-embedding-3-small`, 1536-d, or Gemini `gemini-embedding-001`, 768-d) writing to `ListingEmbedding.vector` (pgvector, HNSW cosine index). Candidate retrieval becomes `ORDER BY vector <=> $want LIMIT 40`, followed by the same deterministic compatibility gate. Switching is controlled by `EMBEDDING_PROVIDER` and needs no other code changes.

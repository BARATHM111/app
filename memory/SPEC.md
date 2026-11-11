# BarterX — Living Spec

## What it does
An AI-assisted barter marketplace. Users list goods or services, post wants that name the listing they offer in return, see semantic match candidates, and propose deterministic 2- or 3-party exchange cycles. Every participant must approve the current revision. Imbalances are settled by PayPal Sandbox balancing payments, and fulfilment is confirmed per participant. Full design is in `/docs`.

## Stack (this workspace)
FastAPI + motor/MongoDB (`backend/`), React 19 + TS + Vite + Tailwind v4 (`frontend/`). All routes are under `/api/v1`. The target port (NestJS, Prisma, Neon) is documented in `/docs`.

## Data model (collections)
users, listings, wants, listing_embeddings, matches, exchanges, exchange_participants, exchange_approvals, offers, payments, notifications. Ids are string UUID-style. See `docs/03-database-erd.md`.

## Auth
Email + password (PBKDF2-SHA256). The JWT is stored in the httpOnly cookie `barterx_session`. `GET /api/v1/auth/session` returns `{user|null}`. There is one role (trader). Ownership is checked on every mutation, and exchange routes are participant-only.

## Key flows
1. Register/login, then create a listing (optionally using AI extraction), then create a want with an offering.
2. `/matches`: semantic candidates (local deterministic embeddings, gated by compatibility rules).
3. `/cycles`: deterministic cycles. Proposing one reserves its listings (409 on conflicts).
4. `/proposal/:id`: approve the current revision. Request-changes increments the revision and resets approvals.
5. Payment (only if your balance > 0 and everyone has approved): tick the authorisation box, then a PayPal order, PayPal approval, and a server capture. Payment is verified only from PayPal's response or a verified webhook.
6. Fulfilment: each participant confirms. When all have confirmed, the exchange is `completed` and the listings become `traded`.

## Seed facts (`cd /app/backend && python seed.py`, idempotent; resets demo exchanges)
- 7 traders: maya, theo, ravi, sana, diego, nia, omar `@barterx.dev`, password `barter1234`.
- Cycles: `c2:usr_diego:usr_sana` (balanced, $260 each way, no payment needed) and `c3:usr_maya:usr_ravi:usr_theo`. In the 3-party cycle Maya owes $30, Ravi owes $40, and Theo is owed $70.

## Integrations
- LLM: Claude `claude-sonnet-4-6` via `EMERGENT_LLM_KEY` (extraction, categorisation, match explanation, deal summary). This is live.
- Embeddings: **local deterministic provider** (no hosted embedding model is available on the managed key).
- PayPal Sandbox: real REST calls are implemented, **but no credentials are configured yet**, so payment creation returns 503 with a clear message.

## Spec deviations
NestJS/Prisma/Postgres/pgvector/Neon are documented but not implemented, because the pod runs FastAPI + MongoDB. Embeddings are local rather than hosted. PayPal is not configured.

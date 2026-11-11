# BarterX: AI-matched multi-party barter with PayPal settlement

## The problem
A direct barter only works when two people each want what the other has. Most trades never happen because
A wants B's item, but B wants something from C.

## What BarterX does
BarterX finds **trade cycles** (A → B → C → A) among people's listings and wants. Each person approves the same
proposal, and **PayPal** settles whatever value difference remains, so an uneven trade can still close fairly.

## How PayPal is used (backend only, Sandbox)
- **Orders v2**: when a trade has an agreed value difference, each participant who owes money gets a PayPal order
  for the exact amount (checkout → approve → server-side capture → verification).
- **Payouts**: once the exchange completes, the participant who is owed money receives a PayPal Payout to their
  saved PayPal email (sent automatically, or when they click "Claim payout").
- **Webhooks**: signature-verified events (`PAYMENT.CAPTURE.*`) sync payment status. Duplicate deliveries are ignored.
- Payment is never faked. If PayPal is not configured, the app says so and blocks payment.

## How AI is used
- **Listing intelligence** (Claude via Emergent universal key): turns a free-text description into category,
  condition, tags, a value range with its basis (labelled *unverified*) and suggested wants. The output is checked against a strict schema.
- **Semantic matching**: listing and want embeddings are scored with cosine similarity, which is 45% of the
  match score. The remaining 55% is deterministic: category, value and location.
- **Match explanations**: a plain-language reason why each trade fits.
- AI only advises. Approvals, balances, payments and state changes are deterministic code.

## The engine
- A directed graph where an edge means "this listing satisfies that want". A bounded DFS finds 2- and 3-person cycles,
  ranked by weakest edge, average edge, value gap and size.
- Exchange lifecycle: Proposed → every participant approves the **same revision** (a counteroffer resets all approvals)
  → payment → each participant confirms fulfilment → Completed. Listings are reserved with atomic claims, so a listing
  can't be committed to two trades at once. Disputes, a 3-day expiry and an admin view are included.
- Reviews and reputation (completed trades only) and in-app alerts when a new listing completes a cycle.

## Stack
React 19 + TypeScript + Tailwind (frontend), FastAPI + MongoDB (running backend), PayPal REST Sandbox,
Claude. A Prisma/PostgreSQL + pgvector schema with migrations (`/prisma`) is the portable Neon target.

## Try it
See `docs/DEMO.md` (accounts and a 7-step walkthrough) and `DEPLOYMENT.md`. Reset the demo with `bash scripts/reset_demo.sh`.
Tests: `cd backend && python -m pytest` (60 pass; 3 pgvector tests need a Postgres URL).

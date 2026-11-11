# 11 — Summary, Implementation Sequence, Risks, Open Questions

## Architecture summary
A modular monolith with 12 modules. LLMs draft and explain. Embeddings rank candidates. Deterministic code validates compatibility, computes balances, discovers 2-/3-cycles, enforces per-revision approvals, locks listings, and advances exchange and payment state only on verified facts.

## What was built and verified in this workspace
- Backend: 12 module routers and services under `/api/v1`, Pydantic validation, global error handlers, JSON logging, and indexes for every queried field.
- Frontend: 11 pages, including the cycle visualiser and deal room.
- Seed: 7 traders, 11 listings and 7 wants. Discovery finds exactly one balanced 2-party cycle (Sana↔Diego) and one 3-party cycle (Maya→Theo→Ravi) with $70 in balancing payments.
- Tests: 22 pytest tests (unit and integration) passing. Frontend `tsc -b` is clean. The browser happy path through the public URL shows zero console errors and no failed requests.

## Implementation sequence (for the NestJS/Prisma port)
1. Scaffold NestJS, the Prisma schema in doc 03, and the first migration (with the vector extension) on a Neon dev branch.
2. Auth and Users (bcrypt/argon2, JWT cookie guard), then the global filter and ValidationPipe.
3. Listings and Wants CRUD with DTOs, ownership guards, and pagination.
4. Port the GraphEngine and Compatibility services as pure providers, along with the unit tests from `test_unit_core.py`.
5. Exchanges state machine, then Notifications.
6. AI adapter (extraction, explanations, summaries) and the embedding provider writing to pgvector.
7. Payments and Webhooks against PayPal Sandbox.
8. Frontend: keep the React app and point it at the same `/api/v1` contract.
9. Deploy to Vercel, Render and Neon (after approval).

## Technical risks
| Risk | Mitigation |
|---|---|
| Race between two proposals reserving the same listing | Service lock check now. In Postgres, a SERIALIZABLE transaction plus a partial unique index |
| Local hashed embeddings are lexical, not truly semantic | Provider interface is ready. Switch to a hosted embedding model with pgvector when a key is available |
| 3-cycle search is O(U³) | Run incrementally per strongly connected component, or as a background job |
| Cancelling after capture leaves money with the merchant | Manual refunds for now. Automate with PayPal refunds later |
| No payouts to traders who are owed money | Ledger only. Payouts need business, legal and KYC review |
| LLM latency and cost | One-shot calls, explanations cached on the Match |

## Questions requiring your approval
1. **PayPal Sandbox credentials**: add `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` (and optionally `PAYPAL_WEBHOOK_ID`) through the secure card. Payments stay disabled (503) until then.
2. **Settlement model**: should traders who are owed money get automatic PayPal Payouts, or should the marketplace keep the ledger-only model?
3. **Hosted embeddings**: do you want to provide an OpenAI or Gemini embedding key so `EMBEDDING_PROVIDER` can switch from local to hosted?
4. **Port timing**: approve moving this implementation to NestJS, Prisma and Neon (that requires a Neon `DATABASE_URL`). No migrations have been run against any external database.
5. **Deployment**: nothing is deployed. Confirm when you want Vercel and Render set up.

# BarterX — Documentation Index

The **implemented runtime** in this workspace is FastAPI + MongoDB + React/TS (the only stack this pod can run and preview). The **target production stack** is NestJS + Prisma + PostgreSQL/pgvector on Neon, Render and Vercel. Every document gives the target design and also maps it to the running code, so moving the code over is a translation job with no redesign needed.

| # | Document | What it covers |
|---|----------|----------------|
| 01 | [Product Requirements](01-product-requirements.md) | Scope, personas, user stories, business rules, MVP cut |
| 02 | [System Architecture](02-system-architecture.md) | Modular monolith, layers, request flow, cross-cutting concerns |
| 03 | [Database ERD](03-database-erd.md) | Prisma schema for Neon/pgvector, relationships, indexes, Mongo mapping |
| 04 | [API Specification](04-api-specification.md) | Every `/api/v1` endpoint, auth, status codes |
| 05 | [Backend Modules](05-backend-modules.md) | The 12 modules, their responsibilities and dependencies |
| 06 | [Frontend Architecture](06-frontend-architecture.md) | Pages, components, data-fetching rules |
| 07 | [AI Integration](07-ai-integration.md) | LLM tasks, embeddings, guard rails |
| 08 | [Graph Matching Algorithm](08-graph-matching-algorithm.md) | Edge construction, 2/3-cycle discovery, balance maths |
| 09 | [PayPal Integration](09-paypal-integration.md) | Orders v2 flow, verification, webhooks, no-escrow statement |
| 10 | [Deployment Architecture](10-deployment-architecture.md) | Vercel/Render/Neon topology, env vars, migrations |
| — | [Summary, risks & open questions](11-summary-and-decisions.md) | Implementation sequence, risks, items needing approval |

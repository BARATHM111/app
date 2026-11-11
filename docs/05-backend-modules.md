# 05 — Backend Module Architecture

The 12 requested modules map to NestJS modules in the target stack and to router/service pairs in this workspace.

| # | NestJS module (target) | Here: router → service | Owns | Depends on |
|---|---|---|---|---|
| 1 | AuthModule | `routers/auth.py` → `lib/security.py` | sessions, hashing, JWT | Users, Database |
| 2 | UsersModule | `routers/users.py` | `users` | Database |
| 3 | ListingsModule | `routers/listings.py` | `listings`, embedding upkeep | AI (embeddings), Exchanges (lock check) |
| 4 | WantsModule | `routers/wants.py` | `wants` | Listings |
| 5 | AIModule | `routers/ai.py` → `services/ai.py`, `lib/embeddings.py` | `listing_embeddings`, match explanations | none (pure adapter) |
| 6 | MatchingModule | `routers/matching.py` → `services/matching.py`, `services/compatibility.py` | `matches` | Listings, Wants, AI (embeddings) |
| 7 | GraphEngineModule | `services/graph.py` (exposed via `/v1/cycles`) | none (read-only, pure) | Compatibility |
| 8 | ExchangesModule | `routers/exchanges.py` → `services/exchanges.py` | `exchanges`, `exchange_participants`, `exchange_approvals`, `offers` | Graph, Notifications |
| 9 | PaymentsModule | `routers/payments.py` → `services/payments.py` | `payments` | Exchanges (state refresh), Notifications |
| 10 | NotificationsModule | `routers/notifications.py` → `services/notifications.py` | `notifications` | Database |
| 11 | WebhooksModule | `routers/webhooks.py` | none | Payments |
| 12 | DatabaseModule | `lib/db.py` (motor + index registry) | connection, indexes | env |

## NestJS layout (target)
```
src/
  main.ts                    // setGlobalPrefix('api'), URI versioning v1, ValidationPipe, cookie-parser
  common/ filters/http-exception.filter.ts · interceptors/logging.interceptor.ts · guards/jwt.guard.ts
  database/ prisma.module.ts · prisma.service.ts
  auth/ users/ listings/ wants/ ai/ matching/ graph-engine/ exchanges/ payments/ notifications/ webhooks/
     each: *.module.ts · *.controller.ts · *.service.ts · dto/*.dto.ts (class-validator) · *.spec.ts
```
Rules: controllers only call services. Services receive dependencies through DI. The graph engine is a pure provider (no Prisma writes), unit-tested with fixtures. The exchange state machine lives in a single `ExchangeStateService.refresh()` that is the only writer of `Exchange.status`.

## Tests (implemented here)
- `backend/tests/test_unit_core.py`: compatibility rules, value maths, embedding determinism, edge construction, 3-cycle balances summing to zero, order-independent cycle keys.
- `backend/tests/test_integration_api.py`: auth, ownership 403s, CRUD with filters and pagination, the full 2-party lifecycle (reservation lock, revision invalidation, payment gating, cancel/release), a balanced cycle completing without payment, and rejection of unauthenticated requests and unverified webhooks. Every test user is purged on teardown.

# 02 — System Architecture

## Style: modular monolith
There is one deployable backend process with strongly separated modules, one database and one frontend SPA. There are no microservices: inter-module calls are in-process function calls through services, not HTTP.

```
 Browser (React SPA, Vercel)
        │  HTTPS, same-site cookie session, relative /api paths
        ▼
 API (NestJS on Render  |  FastAPI in this pod)
   ├─ Controllers / routers   — thin: validate DTO, resolve user, call a service
   ├─ Services                — business logic (deterministic)
   │    compatibility · matching · graph · exchanges · payments · notifications
   ├─ AI adapter              — LLM calls (advisory only) + embedding provider
   ├─ PayPal adapter          — OAuth2, Orders v2, webhook verification
   └─ Data access             — Prisma (target)  |  motor (here)
        ▼
 PostgreSQL + pgvector (Neon)  |  MongoDB (this pod)
```

## Layering rules
- Controllers contain no business logic. In this workspace that means `backend/routers/*`, which only validate input and delegate.
- Business logic lives in services (`backend/services/*`).
- Each service owns its collections/tables. The graph engine only *reads* listings and wants. Only the exchange service writes exchange state, and payments call back into it through `refresh_exchange_state` after a verified capture.
- The AI module has **no import path** into exchange or payment state mutation.

## Cross-cutting concerns
| Concern | Target (NestJS) | Implemented here |
|---|---|---|
| Validation | DTOs + class-validator, global `ValidationPipe({whitelist:true})` | Pydantic v2 models; the 422 handler gives one error shape |
| Auth | Passport JWT guard, httpOnly cookie | `lib/deps.get_current_user`, httpOnly `barterx_session` cookie |
| Errors | Global exception filter | Global handlers in `server.py` (422, 500 with a stable `error` code) |
| Logging | pino / nestjs-pino JSON | `lib/log.py`: one JSON line per event (`listing.created`, `payment.capture_attempted`, …) |
| Config | `@nestjs/config`, env only | `backend/.env` read through `os.environ`. No secrets in the frontend |
| Versioning | `app.setGlobalPrefix('api'); enableVersioning(URI)` | Routers mounted under `/api/v1` |

## Request flow example: propose a cycle
1. `POST /api/v1/exchanges/from-cycle {cycle_key, participant_ids}`
2. The server **re-runs** deterministic discovery and finds the cycle by key. Client-sent values are never trusted.
3. The listing lock is checked (no listing is already in an active exchange). Then the exchange and participants are written and listings are set to `reserved`.
4. The other participants are notified.

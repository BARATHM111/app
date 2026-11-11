# 10 — Deployment Architecture (target)

```
Vercel (React SPA, static)  ──/api rewrite──▶  Render Web Service (NestJS, Node 20)
                                                    │  DATABASE_URL (pooled)  DIRECT_URL (migrations)
                                                    ▼
                                             Neon PostgreSQL + pgvector
                                                    ▲
                     PayPal Sandbox ──webhook──▶ /api/v1/webhooks/paypal
```

- **Same-origin cookies**: Vercel `rewrites` proxy `/api/*` to the Render URL, so the session cookie stays first-party and the frontend keeps calling relative `/api` paths, as it does in this pod.
- **Render**: build with `npm ci && npx prisma generate && npx prisma migrate deploy && npm run build`, start with `node dist/main.js`, and health-check `/api/health`.
- **Neon**: use the pooled connection string for runtime and the direct one for `migrate deploy`. Enable the `vector` extension in the first migration. Use branches for preview environments.
- **Secrets** (Render env): `DATABASE_URL`, `DIRECT_URL`, `JWT_SECRET`, `LLM_API_KEY`, `EMBEDDING_PROVIDER`, `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `PAYPAL_WEBHOOK_ID`, `PAYPAL_API_BASE`, `CORS_ORIGINS`. Vercel holds no secrets.
- **Migrations**: only `prisma migrate deploy` in CI or on Render. `db push` is banned for shared databases. Destructive migrations need manual approval.
- **Observability**: JSON logs go to Render's log stream. Add request ids in an interceptor.

## This workspace
FastAPI (port 8001) and Vite (port 3000), proxied through `/api`, with in-pod MongoDB, all managed by supervisor. Nothing has been deployed (as instructed).

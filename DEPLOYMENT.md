# BarterX deployment guide (nothing has been deployed)

## What actually runs
| Layer | Implemented | Target design (docs/, prisma/) |
|---|---|---|
| Frontend | React 19 + TS + Vite (`frontend/`) | Vercel (same code) |
| Backend | **FastAPI (Python)** (`backend/`) | Render (same code). NestJS is a design target only, not implemented |
| Database | **MongoDB** (motor) | Neon Postgres + Prisma + pgvector. Schema and migrations are in `prisma/` and verified locally, but **not wired into the running backend** |
| Payments | PayPal REST Sandbox (Orders v2, Payouts) | same |

The running backend needs a MongoDB URL (for example Atlas). Neon is only usable once the Prisma
schema is connected to a backend (future milestone). For the vector store,
`EMBEDDING_STORE=pgvector` plus `PGVECTOR_URL` (a Neon URL) makes the embedding store use pgvector today.

## Backend on Render (Web Service)
- Root directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn server:app --host 0.0.0.0 --port $PORT --proxy-headers`
- Health check path: `/api/health` (returns `database: ok | unreachable`)
- Environment: copy `backend/.env.example`. Set `CORS_ORIGINS` to the exact Vercel origin (never `*` in production).
- Mongo client timeouts: 5s server selection and connect. An outage returns 503 in about 5s (verified).
- Logs: JSON lines on stdout (`lib/log.py`), readable in Render's log stream.

## Frontend on Vercel
- Root directory: `frontend`. Build: `yarn build`. Output: `dist`.
- API calls use relative `/api/...`. `frontend/vercel.json` rewrites `/api/*` to the Render URL. **Edit the
  destination host before the first deploy.** Same-origin rewrites keep the httpOnly session cookie first-party, so no
  frontend secret or API base URL is needed. No secret ever ships to the browser.

## Neon + Prisma (target schema)
- `DATABASE_URL` = Neon **pooled** URL (`-pooler` host, `?sslmode=require&pgbouncer=true&connect_timeout=10`).
- `DIRECT_URL` = Neon **direct** URL (migrations need a non-pooled connection).
- Production migrations: `npx prisma migrate deploy --schema prisma/schema.prisma`. Never `prisma db push`.
- pgvector: Neon supports 0.8.0 (Postgres 14-17). Migration 0002 runs `CREATE EXTENSION vector`, HNSW indexes and checks.
  Verified locally against PG 15 + pgvector 0.8.0 with `bash scripts/dev_pgvector.sh` (migrate deploy and zero drift).
  **Not yet verified against a real Neon project** (no Neon credentials were provided).

## PayPal Sandbox
Set `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` and `PAYPAL_WEBHOOK_ID` (sandbox app). Webhook URL:
`https://<render-host>/api/v1/webhooks/paypal`. Subscribe to CHECKOUT.ORDER.APPROVED, PAYMENT.CAPTURE.*, PAYMENT.PAYOUTS-ITEM.*.
Without credentials every payment endpoint returns 503 with an explicit message. Nothing is faked.

### Manual sandbox test
1. In developer.paypal.com, create a sandbox REST app plus a sandbox *personal* buyer account.
2. Add the keys, then run `python backend/seed.py`.
3. Maya proposes the 3-party cycle, and Maya, Theo and Ravi each approve the same revision.
4. Ravi clicks Pay and approves with the sandbox buyer. On return the server captures and verifies.
5. All three confirm fulfilment, then one clicks Complete. The payout to the owed trader is sent and verified by PayPal.

## Post-deploy checklist (run after you approve a deploy)
Frontend loads · `/api/health` returns ok · register and login · create listing · matches · cycles · approvals by all three · PayPal sandbox pay and capture.

## Secrets
`backend/.env` holds local dev values only and must not be committed. Use the `.env.example` templates. A scan found no
PayPal or Neon secrets in the code. The LLM key is read from the environment only.

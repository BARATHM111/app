# 04 — API Specification (`/api/v1`)

- Auth uses an httpOnly cookie, `barterx_session` (a JWT, HS256, 7 days). Tokens never appear in JSON.
- Errors share one shape: `{"detail": string | ValidationError[], "error"?: "validation_error" | "internal_error"}`.
- Status codes: 401 not signed in · 403 not the owner or participant · 404 not found · 409 state conflict (reserved listing, unapproved exchange, duplicate proposal) · 422 validation failure · 502 upstream (AI/PayPal) failure · 503 integration not configured.

| Module | Method & path | Auth | Purpose |
|---|---|---|---|
| Health | `GET /api/health` | – | DB / AI / PayPal configuration status |
| Auth | `POST /v1/auth/register` | – | Create an account and set the session cookie (201, 409 if the email is taken) |
| | `POST /v1/auth/login` | – | Set the session cookie (401 if credentials are wrong) |
| | `POST /v1/auth/logout` | – | Clear the cookie |
| | `GET /v1/auth/me` | ✅ | Current user (401 when anonymous) |
| | `GET /v1/auth/session` | – | `{user: UserMe \| null}`, always 200 |
| Users | `GET/PATCH /v1/users/me` | ✅ | Read/update your profile |
| | `GET /v1/users/{id}` · `/v1/users/{id}/listings` | – | Public profile (no email) and active listings |
| Listings | `GET /v1/listings?page&page_size&type&category&status&q&min_value&max_value&sort&owner_id` | – | Paginated, filtered browse (defaults to `status=active`) |
| | `GET /v1/listings/mine` | ✅ | Own listings, all statuses |
| | `GET /v1/listings/meta/categories` | – | Distinct active categories |
| | `POST /v1/listings` | ✅ | Create (also writes a ListingEmbedding) |
| | `GET /v1/listings/{id}` | – | Detail, including `in_active_exchange` |
| | `PATCH /v1/listings/{id}` · `DELETE` | owner | 409 if the listing is committed to an active exchange |
| Wants | `GET /v1/wants` | ✅ | Own wants plus the listings you can offer |
| | `POST /v1/wants` · `GET/PATCH/DELETE /v1/wants/{id}` | owner | The offered `listing_id` must be your own and uncommitted |
| Matching | `GET /v1/matches` | ✅ | Recompute and return semantic candidates for your wants |
| | `POST /v1/matches/{id}/dismiss` | owner | Hide a candidate |
| Graph | `GET /v1/cycles?max_nodes=2\|3&limit` | – | Deterministic 2-/3-party cycles |
| | `GET /v1/graph/stats` | – | Node, edge and cycle counts |
| Exchanges | `GET /v1/exchanges` | ✅ | Your exchanges (briefs) |
| | `POST /v1/exchanges/from-cycle {cycle_key, participant_ids}` | participant | The server re-derives the cycle. 409 if it is stale, reserved or a duplicate |
| | `GET /v1/exchanges/{id}` | participant | Detail plus the approval ledger and offers |
| | `POST /v1/exchanges/{id}/approve {decision, note}` | participant | Approve the current revision |
| | `POST /v1/exchanges/{id}/request-changes {note}` | participant | Revision +1, all approvals reset |
| | `POST /v1/exchanges/{id}/offers {to_user_id, message, proposed_changes}` | participant | Negotiation message. Non-empty `proposed_changes` creates a new revision |
| | `POST /v1/exchanges/{id}/fulfilment` | participant | Confirm your side was received (409 before approvals and payments are done) |
| | `POST /v1/exchanges/{id}/cancel` | participant | Cancel and release the listings |
| Payments | `GET /v1/payments/config` | – | Whether PayPal is configured, plus the no-escrow note |
| | `POST /v1/exchanges/{id}/payments {return_url, cancel_url}` | payer | **Explicit authorisation.** Creates a PayPal order and returns `approval_url` (503 if not configured) |
| | `POST /v1/payments/{id}/capture` | payer | Server-side capture and verification |
| | `GET /v1/payments/mine` · `GET /v1/payments/{id}` | owner | Payment records |
| AI | `GET /v1/ai/status` | – | Model information |
| | `POST /v1/ai/extract-listing {text}` | ✅ | Structured draft plus warnings and confidence |
| | `POST /v1/ai/categorize {text}` | ✅ | 1–3 categories |
| | `POST /v1/ai/match-explanation {match_id}` | owner | Plain-language explanation (cached) |
| | `POST /v1/ai/deal-summary {exchange_id}` | participant | Summary, open questions, negotiation ideas |
| | `POST /v1/ai/rebuild-embeddings` | – | Recompute ListingEmbedding rows |
| Notifications | `GET /v1/notifications` · `/unread` · `POST /{id}/read` · `POST /read-all` | ✅ | Activity feed |
| Webhooks | `POST /v1/webhooks/paypal` | PayPal signature | Verified via PayPal's verify-webhook-signature (400 if unverified, 503 if not configured) |

Interactive OpenAPI docs are served at `/docs` on the backend (port 8001).

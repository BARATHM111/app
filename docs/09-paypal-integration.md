# 09 — PayPal Integration Design (REST Sandbox, Orders v2)

**PayPal is not an escrow service.** BarterX never says otherwise. Captured sandbox funds settle to the marketplace's sandbox merchant account, and the BarterX ledger records who owes what.

## Credentials (backend env only, never in the frontend)
| Var | Purpose |
|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` | OAuth2 client credentials (sandbox REST app) |
| `PAYPAL_WEBHOOK_ID` | Webhook ID, used for signature verification |
| `PAYPAL_API_BASE` | `https://api-m.sandbox.paypal.com` |

Until these are present, `/v1/payments/config` reports `configured:false`, payment creation returns **503**, and nothing is charged or faked.

## Flow
1. **Gate**: all participants have approved the current revision (status `approved`/`awaiting_payments`) and the caller has `balance > 0`.
2. **Explicit authorisation**: in the UI the payer ticks "I authorise a $X balancing payment" and clicks Pay. That request *is* the authorisation, and no background job ever starts a payment.
3. `POST /v1/oauth2/token` (client credentials) returns a bearer token, cached until expiry.
4. `POST /v2/checkout/orders` with `intent: CAPTURE`, the amount as a two-decimal string and the currency, `reference_id = exchange:participant`, `custom_id = participant`, and the return and cancel URLs. The `Payment` row is stored as `created` with `paypal_order_id`.
5. The browser is redirected to PayPal's `approve` link, where the payer approves.
6. PayPal redirects back to `/proposal/:id?paypal=return`. **The redirect proves nothing.** The page calls `POST /v1/payments/{id}/capture`.
7. The server calls `POST /v2/checkout/orders/{id}/capture`. Only if PayPal reports `status: COMPLETED` with a `COMPLETED` capture whose amount and currency match the agreed balance does the payment become `captured, verified=true, verification_source=capture_api_response`. Anything else becomes `failed`, with PayPal's reason stored in `last_error`.
8. The exchange state refreshes: once every payer is verified, the status moves to `payments_complete`.

## Webhooks (`POST /api/v1/webhooks/paypal`)
- Every event is checked with `POST /v1/notifications/verify-webhook-signature`, using the `paypal-transmission-*`, `paypal-cert-url` and `paypal-auth-algo` headers plus `PAYPAL_WEBHOOK_ID`. Anything other than `SUCCESS` gets a 400 and is ignored.
- `CHECKOUT.ORDER.APPROVED` sets `approved` and `authorized_at`.
- `PAYMENT.CAPTURE.COMPLETED` runs the same amount/currency verification and sets `verified`, with source `webhook`. This makes the flow idempotent if the browser never returns.
- `PAYMENT.CAPTURE.DENIED / REFUNDED / REVERSED` sets `failed` or `refunded` and `verified=false`.

## Separation from fulfilment
Payment verification and fulfilment confirmation are independent fields. Fulfilment unlocks only after the payments are verified, and completion requires every participant's fulfilment.

## Not in the MVP
Payouts to traders who are owed money (this would need PayPal Payouts plus KYC review), automated refunds when an exchange is cancelled after capture (handled manually, flagged as a risk), and live mode.

## Sandbox test plan
Create a sandbox REST app and a personal buyer account at developer.paypal.com. Sign in as `maya@barterx.dev`, get all three seeded traders to approve the 3-party cycle, then pay $30.00 and approve with the sandbox buyer. On return the payment should show "Verified by PayPal".

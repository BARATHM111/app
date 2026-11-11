# 01 — Product Requirements Document

## Problem
People hold things and skills they would trade, but direct barter rarely works: A wants what B has, and B wants something A doesn't have. BarterX finds **multi-party cycles** (A→B→C→A) so that everyone's want gets filled. When the values in a cycle don't balance, the difference is settled with a small cash payment.

## Personas
- **Maker / owner of goods**: lists a physical item such as furniture, a camera or an espresso machine.
- **Professional**: lists a service such as web development, brand design or contract review.
- Most users are both: they list something and say what they want in return.

## MVP scope (solo developer)
| Area | In MVP | Status in this workspace |
|---|---|---|
| Register / login (JWT, hashed passwords) | ✅ | Implemented: httpOnly cookie JWT, PBKDF2-SHA256 |
| Profile management | ✅ | Implemented |
| Listing CRUD (goods + services) with pagination and filters | ✅ | Implemented |
| Want CRUD tied to an offered listing | ✅ | Implemented |
| AI listing extraction and categorisation | ✅ | Implemented (Claude via the Emergent universal key) |
| Semantic matching with embeddings | ✅ | Implemented. Embeddings are a **deterministic local provider** (see 07) |
| 2- and 3-person cycle discovery (deterministic) | ✅ | Implemented |
| Proposal review, negotiation messages, approvals | ✅ | Implemented. Any change invalidates earlier approvals |
| Balancing payments via PayPal Sandbox | ✅ | Implemented with real API calls; **disabled until sandbox credentials are added** |
| Fulfilment confirmation and completion | ✅ | Implemented. Tracked separately from payment |
| Notifications feed | ✅ | Implemented (in-app only) |
| Email/push, ratings, disputes, shipping, chat | ❌ | Out of scope |

## Core business rules (enforced in code)
1. A user can have many listings and many wants.
2. Listings are `goods` or `services`.
3. AI values are **suggestions**, never verified valuations. The UI labels them that way.
4. Semantic matching yields **candidates**. Deterministic compatibility checks gate every candidate.
5. Cycle discovery is deterministic: the same input always gives the same cycles.
6. An exchange needs **every** participant's approval **for the current revision**.
7. Requesting changes, or posting an offer with `proposed_changes`, increments the revision and resets all approvals.
8. A listing can belong to only **one** non-terminal exchange. Proposing a conflicting cycle returns 409. Re-pricing, pausing or deleting a committed listing also returns 409.
9. A payment can only be created by a signed-in participant who explicitly ticks the authorisation box and clicks Pay.
10. A payment is marked `captured`/`verified` **only** from PayPal's own server response (the capture API) or a signature-verified webhook. Returning to the app from PayPal is never treated as proof.
11. The product never claims PayPal provides escrow (stated in the UI and in the API config response).
12. Fulfilment (goods or service handed over) and payment completion are separate states.

## Exchange lifecycle
`proposed → approved | awaiting_payments → payments_complete → completed`, and `cancelled` can be reached from any non-completed state.
- If everyone approves and nobody owes money, the exchange goes to `approved`.
- If everyone approves and someone owes money, it goes to `awaiting_payments`, then to `payments_complete` once every required payment is verified.
- When every participant confirms fulfilment, it goes to `completed`. The listings become `traded` and the wants are closed.

## Success criteria
- A seeded 3-person cycle can be proposed, approved by all three, and completed through the UI.
- No code path marks a payment successful without PayPal's confirmation.
- No code path lets AI output change exchange or payment state.

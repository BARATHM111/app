# Hackathon demo walkthrough

Reset first: `bash /app/scripts/reset_demo.sh` (idempotent. It re-seeds demo users, listings and wants, and clears
demo exchanges, payments, payouts and reservations. Non-demo data is untouched.)

## Accounts (password `barter1234`)
| Trader | Offers | Wants |
|---|---|---|
| maya@barterx.dev | Handcrafted walnut writing desk ($450) | Brand identity design |
| theo@barterx.dev | Vintage 35mm rangefinder camera kit ($520) | Solid wood desk |
| ravi@barterx.dev | Brand identity design package ($480) | Film camera |
Admin (disputes): admin@barterx.dev / `BarterAdmin!2026`. A balanced 2-party swap also exists: sana@ and diego@.

The cycle is Maya → Theo (desk), Theo → Ravi (camera), Ravi → Maya (branding). The values differ, so the
deterministic balances are Maya +30 (pays), Theo −70 (is owed), Ravi +40 (pays). They sum to zero.

## Script
1. **AI analysis**: Create listing, paste a description, click Analyze. Fields, value basis and suggested wants
   appear. The AI value is labelled unverified.
2. **Semantic matching**: Matches page. Each card shows the 45/25/20/10 score breakdown and an AI explanation on request.
3. **Graph engine**: Cycles page. The 3-party cycle (rank #2, behind the balanced swap) shows reasons, scores and a flow diagram.
4. **Proposal**: As Maya, click Propose. The status is Proposed and the listings are reserved.
5. **Approvals**: Maya, Theo and Ravi each sign in and approve **revision 1** (the UI shows the revision). Optionally
   send a counteroffer to show that every approval resets to revision 2.
6. **Payment** (needs PayPal sandbox keys): the payers click Pay, approve on PayPal Sandbox, and are verified server-side on return.
   Without keys the Pay action returns a clear "PayPal not configured" message. No payment is ever simulated.
7. **Fulfilment and completion**: each participant confirms fulfilment, then anyone clicks Complete. Payouts go to the owed trader.

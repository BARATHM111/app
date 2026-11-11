# 08 — Graph-Based Matching Algorithm Design

Everything here is deterministic. Same inputs, same cycles, same order. Implemented in `backend/services/graph.py` and `services/compatibility.py`.

## 1. Inputs
- **Listings**: `status = active` and not committed to a non-terminal exchange (the lock set).
- **Wants**: `status = open` **and** linked to an offering listing that is itself in the active, unlocked set. A want with no offering cannot join a cycle, because the trader would give nothing.

## 2. Edge construction
A directed edge `giver → receiver` exists when some listing L owned by the giver passes `check_compatibility(L, want)` for one of the receiver's wants:
- type matches `target_type` (or the want accepts `any`)
- category matches when the want specifies one (case-insensitive)
- the currency is identical
- `min_value ≤ L.estimated_value ≤ max_value`
- the giver is not the receiver, and L is active

When several listings qualify for one (giver, receiver) pair, one edge is kept, chosen by the tuple `(−semantic_score, |value − reference_value(want)|, listing_id)`. That makes ties impossible.

## 3. Cycle discovery
Users are sorted by id.
- **2-cycles**: for every pair `a < b`, keep the cycle if edges `a→b` and `b→a` both exist.
- **3-cycles**: for every triple `a < b < c`, check both orientations, `a→b→c→a` and `a→c→b→a`. If both exist, keep the one with the lower `(total_imbalance, −mean_semantic)`.
- The cycle key is `c{n}:` followed by the sorted participant ids, so rotations collapse to one key.
- Results are sorted by `(total_imbalance asc, mean_semantic desc, key)` and limited.

Complexity is O(U³) for triples over the users who appear in edges. That is fine for an MVP (hundreds of active traders). For scale, run discovery in a background job only over the strongly connected components that contain changed nodes, and persist candidate cycles.

## 4. Value and balance maths
For participant *i*: `gives_value` is their listing's value and `receives_value` is the value of the listing coming to them.
`balance_i = round2(receives_value − gives_value)`.
- `balance > 0`: they received more value and **owe** a balancing payment.
- `balance < 0`: they are owed money.
- `Σ balance_i = 0` always (unit-tested).
`total_imbalance = Σ |balance_i|`.

Example (seed): Maya gives 450 and gets 480, so she owes 30. Theo gives 520 and gets 450, so he is owed 70. Ravi gives 480 and gets 520, so he owes 40.

## 5. Proposal safety
At proposal time the server **recomputes** the cycles and finds the requested one by key and participant set. Client-sent numbers are ignored. It then verifies that no listing is locked (409 otherwise) and that there is a single currency.

## 6. Settlement model
Payers pay their own `balance` through PayPal to the marketplace sandbox merchant. The exchange is ledger-based: payouts to traders who are owed money are **not** automated in this MVP (see the open questions in 11).

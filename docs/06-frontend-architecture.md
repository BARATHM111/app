# 06 — Frontend Page & Component Architecture

React 19 + TypeScript (strict) + Vite + Tailwind v4 + shadcn/ui (base-ui). Data flows through TanStack Query, and every call goes through `src/lib/api.ts` with relative `/api` paths. No secrets are in the bundle. Auth is a cookie, and `lib/session.ts` owns sign-in/out and clears the query cache.

## Pages (`src/pages`)
| Route | Page | Data |
|---|---|---|
| `/` | Home: hero, static cycle showcase, live graph stats | `GET /v1/graph/stats` (non-blocking) |
| `/login`, `/register` | Split auth layouts | auth endpoints |
| `/marketplace` | Filters (search, kind, category, value range, sort) and a bento grid with pagination | `GET /v1/listings` |
| `/listing/:id` | Listing detail | `GET /v1/listings/{id}` |
| `/create-listing` | AI listing reader (paste → extract → review) and the listing form | `POST /v1/ai/extract-listing`, `POST /v1/listings` |
| `/wants` | Want list and want form with "what you offer in return" | wants CRUD |
| `/matches` | Semantic candidates with deterministic reasons, meters, and on-demand AI explanation | `GET /v1/matches`, `POST /v1/ai/match-explanation` |
| `/cycles` | Discovered 2-/3-party cycles, SVG graph, balance table, Propose button | `GET /v1/cycles`, `POST /v1/exchanges/from-cycle` |
| `/proposal/:id` | Deal room: approval ledger, request-changes, negotiation history, payment panel (explicit authorisation checkbox), fulfilment, AI deal summary | exchange, payment and AI endpoints |
| `/dashboard` | Tiles plus my listings, live proposals and wants | several |
| `/notifications` | Feed with mark read / mark all | notifications |

## Shared components (`src/components`)
`AppShell` (sticky glass nav, unread badge, sign-out, toaster) · `CycleGraph` (deterministic SVG, 2 nodes in a line or 3 in a loop, value labels, balance colours) · `ListingCard` · `MatchCard` · `Badges` (Type/Category/Status/CycleSize).

## Rules
- No page is gated on a fetch. The shell and static copy always render, and the data regions show empty, skeleton or error states.
- Every interactive element and every displayed value has a kebab-case `data-testid`.
- `src/lib/types.ts` mirrors every Pydantic model by hand. In the target stack these become types generated from NestJS's OpenAPI output.

"""Idempotent demo data for BarterX.

    cd /app/backend && python seed.py

Creates seven traders with listings, wants, embeddings and a match feed. The wants
are deliberately wired so the deterministic graph engine finds exactly two cycles:

  * a balanced two-person swap  (Sana's audio mixer <-> Diego's ceramic dinner set, both 260 USD)
  * an imbalanced three-person cycle (Maya -> Theo -> Ravi -> Maya) with balancing payments

Only records belonging to these seeded ids are touched; nothing else is dropped.
"""

import asyncio
import logging

from lib.db import db, ensure_indexes
from lib.dates import utc_now
from lib.security import hash_password
from services.matching import compute_matches_for_user

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("barterx.seed")

DEMO_PASSWORD = "barter1234"

USERS = [
    {
        "id": "usr_maya",
        "name": "Maya Okafor",
        "email": "maya@barterx.dev",
        "bio": "Furniture maker in East Austin. I trade pieces I have finished for work I need done.",
        "location": "Austin, TX",
        "skills": ["Woodworking", "Furniture design"],
    },
    {
        "id": "usr_theo",
        "name": "Theo Lindqvist",
        "email": "theo@barterx.dev",
        "bio": "Analog photography collector. Cameras in, cameras out.",
        "location": "Portland, OR",
        "skills": ["Photography", "Camera repair"],
    },
    {
        "id": "usr_ravi",
        "name": "Ravi Anand",
        "email": "ravi@barterx.dev",
        "bio": "Brand designer working remotely. I trade identity work for things I can use.",
        "location": "Remote",
        "skills": ["Brand identity", "Art direction"],
    },
    {
        "id": "usr_sana",
        "name": "Sana Petrova",
        "email": "sana@barterx.dev",
        "bio": "Studio engineer. Vintage audio gear is my barter currency.",
        "location": "Chicago, IL",
        "skills": ["Audio engineering"],
    },
    {
        "id": "usr_diego",
        "name": "Diego Marin",
        "email": "diego@barterx.dev",
        "bio": "Ceramicist in Santa Fe. Every kiln load has a few pieces looking for a new home.",
        "location": "Santa Fe, NM",
        "skills": ["Ceramics", "Glazing"],
    },
    {
        "id": "usr_nia",
        "name": "Nia Bennett",
        "email": "nia@barterx.dev",
        "bio": "Full-stack developer. I trade build sprints for objects I would otherwise buy.",
        "location": "Denver, CO",
        "skills": ["React", "FastAPI", "Postgres"],
    },
    {
        "id": "usr_omar",
        "name": "Omar Haddad",
        "email": "omar@barterx.dev",
        "bio": "Cafe owner clearing out spare equipment.",
        "location": "Brooklyn, NY",
        "skills": ["Hospitality", "Espresso machines"],
    },
]

ADMIN = {
    "id": "usr_admin",
    "name": "BarterX Admin",
    "email": "admin@barterx.dev",
    "bio": "Dispute oversight.",
    "location": "",
    "skills": [],
    "role": "admin",
}
ADMIN_PASSWORD = "BarterAdmin!2026"

LISTINGS = [
    {
        "id": "lst_maya_desk",
        "owner_id": "usr_maya",
        "title": "Handcrafted walnut writing desk",
        "description": "Solid black walnut writing desk, 120x60cm, hand-cut dovetail drawers and a "
        "hardwax oil finish. Built this year in my Austin workshop; one small knot on the left apron.",
        "type": "goods",
        "category": "Furniture",
        "condition": "Excellent - handmade, one minor knot",
        "estimated_value": 450.0,
        "tags": ["walnut", "desk", "handmade", "furniture"],
        "location": "Austin, TX",
    },
    {
        "id": "lst_theo_camera",
        "owner_id": "usr_theo",
        "title": "Vintage 35mm rangefinder camera kit",
        "description": "1968 rangefinder body with 40mm f/1.7 lens, leather half-case, two extra "
        "rolls and a freshly serviced shutter. Fully working, light brassing on the top plate.",
        "type": "goods",
        "category": "Photography",
        "condition": "Very good - serviced, cosmetic wear",
        "estimated_value": 520.0,
        "tags": ["camera", "35mm", "vintage", "lens"],
        "location": "Portland, OR",
    },
    {
        "id": "lst_ravi_brand",
        "owner_id": "usr_ravi",
        "title": "Brand identity design package",
        "description": "Complete identity sprint: logo suite, type system, colour palette, plus a "
        "20-page brand guideline PDF. Two revision rounds included, delivered in three weeks.",
        "type": "services",
        "category": "Design",
        "condition": "Professional service",
        "estimated_value": 480.0,
        "tags": ["branding", "identity", "design", "logo"],
        "location": "Remote",
    },
    {
        "id": "lst_sana_mixer",
        "owner_id": "usr_sana",
        "title": "Vintage 12-channel analog mixer",
        "description": "Twelve-channel analog desk mixer, recapped last year, all faders smooth. "
        "Great for a home studio; heavy so local pickup preferred.",
        "type": "goods",
        "category": "Audio",
        "condition": "Very good - recapped",
        "estimated_value": 260.0,
        "tags": ["mixer", "analog", "studio", "audio"],
        "location": "Chicago, IL",
    },
    {
        "id": "lst_diego_ceramics",
        "owner_id": "usr_diego",
        "title": "Hand-thrown ceramic dinner set for four",
        "description": "Sixteen pieces: four dinner plates, four bowls, four side plates and four "
        "mugs in a speckled oatmeal glaze. Dishwasher safe, no chips.",
        "type": "goods",
        "category": "Crafts & Pottery",
        "condition": "New - studio seconds, no chips",
        "estimated_value": 260.0,
        "tags": ["ceramics", "pottery", "dinnerware", "handmade"],
        "location": "Santa Fe, NM",
    },
    {
        "id": "lst_nia_sprint",
        "owner_id": "usr_nia",
        "title": "Full-stack web development sprint",
        "description": "Two-week build sprint: TypeScript frontend, typed API, database schema, CI "
        "and a handover walkthrough. Ideal for a marketplace or booking flow.",
        "type": "services",
        "category": "Web Development",
        "condition": "Professional service",
        "estimated_value": 900.0,
        "tags": ["web", "development", "typescript", "api"],
        "location": "Denver, CO",
    },
    {
        "id": "lst_omar_espresso",
        "owner_id": "usr_omar",
        "title": "Rancilio Silvia espresso machine",
        "description": "Single-boiler espresso machine, PID retrofitted, new group gasket and "
        "shower screen. Pulls consistent shots; small dent on the drip tray housing.",
        "type": "goods",
        "category": "Home & Kitchen",
        "condition": "Good - PID mod, small dent",
        "estimated_value": 420.0,
        "tags": ["espresso", "coffee", "machine", "kitchen"],
        "location": "Brooklyn, NY",
    },
    {
        "id": "lst_nia_chair",
        "owner_id": "usr_nia",
        "title": "Ergonomic office chair",
        "description": "Adjustable lumbar office chair with mesh back and four-dimensional "
        "armrests. Used for a year, all mechanisms tight.",
        "type": "goods",
        "category": "Furniture",
        "condition": "Good - one year of use",
        "estimated_value": 320.0,
        "tags": ["chair", "office", "ergonomic"],
        "location": "Denver, CO",
    },
    {
        "id": "lst_ravi_legal",
        "owner_id": "usr_ravi",
        "title": "Contract review and redlining",
        "description": "Review of one commercial agreement up to 25 pages with a redlined copy and "
        "a plain-language summary of the risks, delivered within five working days.",
        "type": "services",
        "category": "Legal & Admin",
        "condition": "Professional service",
        "estimated_value": 250.0,
        "tags": ["contract", "legal", "review", "admin"],
        "location": "Remote",
    },
    {
        "id": "lst_maya_copy",
        "owner_id": "usr_maya",
        "title": "Copywriting retainer - five articles",
        "description": "Five researched articles of 900-1200 words each, SEO-aware structure, two "
        "revision rounds, delivered over six weeks.",
        "type": "services",
        "category": "Writing & Copywriting",
        "condition": "Professional service",
        "estimated_value": 350.0,
        "tags": ["copywriting", "content", "seo"],
        "location": "Remote",
    },
    {
        "id": "lst_omar_printer",
        "owner_id": "usr_omar",
        "title": "3D printer kit with filament bundle",
        "description": "Bed-slinger 3D printer kit, assembled and trammed, plus six spools of PLA in "
        "mixed colours. Ideal first machine.",
        "type": "goods",
        "category": "Electronics",
        "condition": "Good - assembled and calibrated",
        "estimated_value": 380.0,
        "tags": ["3d printer", "maker", "electronics", "filament"],
        "location": "Brooklyn, NY",
    },
]

WANTS = [
    {
        "id": "wnt_maya_brand",
        "user_id": "usr_maya",
        "title": "Brand identity for my furniture studio",
        "description": "I need a proper identity: logo, type system and a guideline document I can "
        "hand to print shops.",
        "category": "Design",
        "target_type": "services",
        "min_value": 400.0,
        "max_value": 550.0,
        "keywords": ["branding", "identity", "design", "logo"],
        "listing_id": "lst_maya_desk",
    },
    {
        "id": "wnt_theo_desk",
        "user_id": "usr_theo",
        "title": "Solid wood desk for the darkroom office",
        "description": "Looking for a handmade wooden desk with drawers, walnut or oak preferred.",
        "category": "Furniture",
        "target_type": "goods",
        "min_value": 400.0,
        "max_value": 600.0,
        "keywords": ["desk", "walnut", "wood", "furniture", "handmade"],
        "listing_id": "lst_theo_camera",
    },
    {
        "id": "wnt_ravi_camera",
        "user_id": "usr_ravi",
        "title": "Working 35mm camera for brand photography",
        "description": "A serviced analog rangefinder I can shoot mockups and print work with.",
        "category": "Photography",
        "target_type": "goods",
        "min_value": 450.0,
        "max_value": 600.0,
        "keywords": ["camera", "35mm", "analog", "rangefinder", "photography"],
        "listing_id": "lst_ravi_brand",
    },
    {
        "id": "wnt_sana_ceramics",
        "user_id": "usr_sana",
        "title": "Ceramic dinner set for the studio kitchen",
        "description": "Handmade stoneware plates, bowls and mugs for four people.",
        "category": "Crafts & Pottery",
        "target_type": "goods",
        "min_value": 240.0,
        "max_value": 300.0,
        "keywords": ["ceramics", "pottery", "dinnerware", "stoneware"],
        "listing_id": "lst_sana_mixer",
    },
    {
        "id": "wnt_diego_mixer",
        "user_id": "usr_diego",
        "title": "Analog mixer for the kiln room recording setup",
        "description": "Studio mixer with clean faders for recording glaze-testing sessions.",
        "category": "Audio",
        "target_type": "goods",
        "min_value": 240.0,
        "max_value": 300.0,
        "keywords": ["mixer", "analog", "studio", "audio", "recording"],
        "listing_id": "lst_diego_ceramics",
    },
    {
        "id": "wnt_nia_chair",
        "user_id": "usr_nia",
        "title": "Ergonomic office chair",
        "description": "Something supportive for long build sprints, mesh back preferred.",
        "category": "Furniture",
        "target_type": "goods",
        "min_value": 200.0,
        "max_value": 400.0,
        "keywords": ["chair", "office", "ergonomic", "mesh"],
        "listing_id": "lst_nia_sprint",
    },
    {
        "id": "wnt_omar_printer",
        "user_id": "usr_omar",
        "title": "3D printer for replacement cafe parts",
        "description": "A reliable printer to make small replacement parts instead of importing them.",
        "category": "Electronics",
        "target_type": "goods",
        "min_value": 300.0,
        "max_value": 500.0,
        "keywords": ["3d printer", "maker", "filament", "electronics"],
        "listing_id": "lst_omar_espresso",
    },
]


async def _upsert(collection: str, doc: dict) -> None:
    await db[collection].update_one({"id": doc["id"]}, {"$set": doc}, upsert=True)


async def _reset_demo_state() -> None:
    """Return the demo traders to a clean pre-trade state.

    Scoped strictly to the seeded demo users/cycles: any exchange between them is
    removed along with its approvals, offers, payments and participants, and their
    listings are put back on the market. Nothing outside the demo data is touched.
    """
    demo_user_ids = [user["id"] for user in USERS]
    exchanges = await db.exchanges.find({"participant_ids": {"$in": demo_user_ids}}).to_list(200)
    exchange_ids = [exchange["id"] for exchange in exchanges]
    if exchange_ids:
        await db.exchanges.delete_many({"id": {"$in": exchange_ids}})
        await db.exchange_participants.delete_many({"exchange_id": {"$in": exchange_ids}})
        await db.exchange_approvals.delete_many({"exchange_id": {"$in": exchange_ids}})
        await db.offers.delete_many({"exchange_id": {"$in": exchange_ids}})
        await db.payments.delete_many({"exchange_id": {"$in": exchange_ids}})
        await db.payouts.delete_many({"exchange_id": {"$in": exchange_ids}})
        await db.exchange_events.delete_many({"exchange_id": {"$in": exchange_ids}})
        await db.listing_reservations.delete_many({"exchange_id": {"$in": exchange_ids}})
    await db.cycle_rejections.delete_many({"user_id": {"$in": demo_user_ids}})
    await db.listing_reservations.delete_many({"listing_id": {"$in": [listing["id"] for listing in LISTINGS]}})
    await db.listings.update_many(
        {"id": {"$in": [listing["id"] for listing in LISTINGS]}},
        {"$set": {"status": "active", "updated_at": utc_now()}},
    )
    await db.wants.update_many(
        {"id": {"$in": [want["id"] for want in WANTS]}}, {"$set": {"status": "open"}}
    )
    logger.info("reset %d demo exchanges and released demo listings", len(exchange_ids))


async def main() -> None:
    now = utc_now()
    await _reset_demo_state()

    admin = {**ADMIN, "password_hash": hash_password(ADMIN_PASSWORD), "created_at": now, "updated_at": now}
    await _upsert("users", admin)
    logger.info("admin %s", ADMIN["email"])
    for user in USERS:
        doc = dict(user)
        doc["password_hash"] = hash_password(DEMO_PASSWORD)
        doc.setdefault("bio", "")
        doc.setdefault("location", "")
        doc.setdefault("skills", [])
        doc["updated_at"] = now
        existing = await db.users.find_one({"id": doc["id"]})
        doc["created_at"] = (existing or {}).get("created_at", now)
        await _upsert("users", doc)
        logger.info("user  %s  %s", doc["id"], doc["email"])

    for listing in LISTINGS:
        doc = dict(listing)
        doc.setdefault("condition", "")
        doc.setdefault("tags", [])
        doc.setdefault("location", "")
        doc["currency"] = "USD"
        doc["status"] = "active"
        doc["ai_assisted"] = False
        doc["updated_at"] = now
        existing = await db.listings.find_one({"id": doc["id"]})
        doc["created_at"] = (existing or {}).get("created_at", now)
        await _upsert("listings", doc)
        logger.info("listing %s  %s", doc["id"], doc["title"])

    for want in WANTS:
        doc = dict(want)
        doc["currency"] = "USD"
        doc["status"] = "open"
        doc["updated_at"] = now
        existing = await db.wants.find_one({"id": doc["id"]})
        doc["created_at"] = (existing or {}).get("created_at", now)
        await _upsert("wants", doc)
        logger.info("want  %s  %s", doc["id"], doc["title"])

    # Vectors for every listing and want, written through the configured provider and store.
    from services.embeddings import reembed_all

    logger.info("embeddings %s", await reembed_all())

    for user in USERS:
        matches = await compute_matches_for_user(user["id"])
        logger.info("matches %s -> %d", user["id"], len(matches))

    await ensure_indexes()
    logger.info("Seed complete. Password for every demo account: %s", DEMO_PASSWORD)
    logger.info("Balanced 2-person cycle: sana <-> diego. 3-person cycle: maya -> theo -> ravi.")


if __name__ == "__main__":
    asyncio.run(main())

"""FastAPI bootstrap: api_router under /api, every module router folded in above the include."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from pymongo.errors import PyMongoError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# MongoDB connection
from lib.db import client, db, ensure_indexes
from lib.log import configure_logging, log_event
from routers import admin as admin_module
from routers import ai as ai_module
from routers import auth as auth_module
from routers import exchanges as exchanges_module
from routers import listings as listings_module
from routers import matching as matching_module
from routers import notifications as notifications_module
from routers import payments as payments_module
from routers import payouts as payouts_module
from routers import reviews as reviews_module
from routers import users as users_module
from routers import wants as wants_module
from routers import webhooks as webhooks_module

configure_logging()
logger = logging.getLogger("barterx")


# Startup runs before the yield, shutdown after it. Add your own setup/teardown here.
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.index_task = asyncio.create_task(ensure_indexes())  # background: a big index build must not block boot
    log_event(logger, "app.startup", db=os.environ.get("DB_NAME"))
    yield
    app.state.index_task.cancel()  # stop a build still running before its client closes
    with suppress(asyncio.CancelledError):
        await app.state.index_task
    client.close()


app = FastAPI(
    title="BarterX API",
    version="1.0.0",
    description=(
        "AI-assisted barter exchange marketplace. LLMs draft and explain; deterministic code "
        "validates compatibility, computes values, discovers cycles and moves state."
    ),
    lifespan=lifespan,
)

api_router = APIRouter(prefix="/api")


@api_router.get("/")
async def root():
    return {"service": "BarterX API", "version": "v1", "docs": "/docs"}


@api_router.get("/health")
async def health():
    """Reports which capabilities are wired up — never a fake success."""
    database_ok = True
    try:
        await client.admin.command("ping")
    except Exception as exc:  # a health check must answer, not raise
        database_ok = False
        log_event(logger, "health.db_error", error=str(exc)[:200])

    from services.ai import is_available as ai_available
    from services.payments import config_status as payment_config

    payments = payment_config()
    return {
        "status": "ok" if database_ok else "degraded",
        "database": "ok" if database_ok else "unreachable",
        "ai": "configured" if ai_available() else "not_configured",
        "payments": {
            "configured": payments.configured,
            "environment": payments.environment,
        },
    }


# Legacy skeleton probe — harmless and kept so nothing that already calls it breaks.
@api_router.post("/status")
async def create_status_check():
    return {"status": "ok"}


# Every module router is mounted on the /api router, versioned under /api/v1.
for module_router in (
    auth_module.router,
    reviews_module.router,  # before users: /{user_id}/reputation must not be shadowed
    users_module.router,
    listings_module.router,
    wants_module.router,
    ai_module.router,
    matching_module.router,
    exchanges_module.router,
    payments_module.router,
    payments_module.exchange_router,
    payouts_module.router,
    admin_module.router,
    payouts_module.exchange_router,
    notifications_module.router,
    webhooks_module.router,
):
    api_router.include_router(module_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Same shape FastAPI uses (with a stable machine-readable error code)."""
    return JSONResponse(
        status_code=422,
        content={
            "detail": jsonable_encoder(exc.errors(), custom_encoder={Exception: str}),
            "error": "validation_error",
            "path": str(request.url.path),
        },
    )


@app.exception_handler(PyMongoError)
async def database_error_handler(request: Request, exc: PyMongoError):
    logger.error("database.unavailable path=%s error=%s", request.url.path, type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is temporarily unavailable. Please retry shortly.", "error": "database_unavailable", "path": str(request.url.path)},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log_event(logger, "error.unhandled", path=str(request.url.path), error=str(exc)[:500])
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": "internal_error", "path": str(request.url.path)},
    )


# Include the router in the main app — keep this the last route registration.
app.include_router(api_router)

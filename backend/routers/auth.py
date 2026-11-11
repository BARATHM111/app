"""AuthModule — registration, login, logout and session introspection.

A JWT is issued on register/login and stored in an httpOnly cookie; tokens never
appear in a JSON body and no password or hash is ever returned.
"""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status as http_status
from pymongo.errors import DuplicateKeyError

from lib.db import db
from lib.dates import clean_doc, utc_now
from lib.deps import get_current_user, get_optional_user
from lib.log import log_event
from lib.security import (
    clear_session_cookie,
    create_access_token,
    hash_password,
    set_session_cookie,
    verify_password,
)
from models.common import MessageResponse
from models.users import SessionResponse, UserCreate, UserLogin, UserMe

router = APIRouter(prefix="/v1/auth", tags=["auth"])
logger = logging.getLogger("barterx.auth")


def _me(user: dict) -> UserMe:
    payload = clean_doc(dict(user))
    payload.pop("password_hash", None)
    return UserMe(**payload)


@router.post("/register", response_model=UserMe, status_code=http_status.HTTP_201_CREATED)
async def register(payload: UserCreate, response: Response):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )
    doc = {
        "id": f"usr_{uuid4().hex[:12]}",
        "name": payload.name.strip(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "bio": payload.bio,
        "location": payload.location,
        "skills": payload.skills,
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    try:
        await db.users.insert_one(dict(doc))
    except DuplicateKeyError as exc:  # unique email index catches the race
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        ) from exc

    set_session_cookie(response, create_access_token(doc["id"], doc["email"]))
    log_event(logger, "auth.registered", user_id=doc["id"])
    return _me(doc)


@router.post("/login", response_model=UserMe)
async def login(payload: UserLogin, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user.get("password_hash", "")):
        log_event(logger, "auth.login_failed", email=email)
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    set_session_cookie(response, create_access_token(user["id"], user["email"]))
    log_event(logger, "auth.login", user_id=user["id"])
    return _me(user)


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    clear_session_cookie(response)
    return MessageResponse(message="Signed out")


@router.get("/me", response_model=UserMe)
async def me(user: dict = Depends(get_current_user)):
    return _me(user)


@router.get("/session", response_model=SessionResponse)
async def session(user: dict | None = Depends(get_optional_user)):
    """Signed-out is a normal state, not an error: always 200, `user` is null when anonymous."""
    return SessionResponse(user=_me(user) if user else None)

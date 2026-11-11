"""Shared FastAPI dependencies — session resolution and ownership checks."""

from fastapi import Cookie, HTTPException, status

from lib.db import db
from lib.security import SESSION_COOKIE, decode_access_token


async def _user_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    user = await db.users.find_one({"id": payload.get("sub")})
    return user


async def get_optional_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict | None:
    """Public routes: returns the user when a valid session exists, else None."""
    return await _user_from_token(token)


async def get_current_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = await _user_from_token(token)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


async def get_admin_user(token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    user = await get_current_user(token)
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def require_owner(resource: dict, user: dict, resource_name: str = "resource") -> None:
    """Ownership validation for every mutating route."""
    if resource.get("owner_id") != user["id"] and resource.get("user_id") != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You do not own this {resource_name}",
        )

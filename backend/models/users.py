"""User request/response models. `password_hash` never leaves the database layer."""

from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    bio: str = Field(default="", max_length=1000)
    location: str = Field(default="", max_length=120)
    skills: List[str] = Field(default_factory=list)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    bio: str | None = Field(default=None, max_length=1000)
    location: str | None = Field(default=None, max_length=120)
    skills: List[str] | None = None
    # Where balancing payouts are sent. Empty string clears it (payouts then use the login email).
    paypal_email: EmailStr | Literal[""] | None = None


class UserPublic(BaseModel):
    """What anyone can see about another trader — never the email."""

    id: str
    name: str
    bio: str = ""
    location: str = ""
    skills: List[str] = Field(default_factory=list)
    created_at: datetime


class UserMe(BaseModel):
    id: str
    name: str
    email: str
    paypal_email: str | None = None
    role: str = "trader"
    bio: str = ""
    location: str = ""
    skills: List[str] = Field(default_factory=list)
    created_at: datetime


class UserBrief(BaseModel):
    """Compact owner reference embedded in listings, matches and exchanges."""

    id: str
    name: str
    location: str = ""


class SessionResponse(BaseModel):
    user: UserMe | None = None

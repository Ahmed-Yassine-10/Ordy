from __future__ import annotations

import uuid

from ordy_core.enums import MemberRole, RestaurantStatus
from pydantic import BaseModel, EmailStr, Field


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = "Africa/Tunis"
    currency: str = Field(default="TND", min_length=3, max_length=3)
    default_language: str = "fr"


class RestaurantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = None
    default_language: str | None = None
    languages: list[str] | None = None
    voice_enabled: bool | None = None


class RestaurantOut(BaseModel):
    id: uuid.UUID
    slug: str
    name: str
    status: RestaurantStatus
    timezone: str
    currency: str
    default_language: str
    languages: list[str]
    voice_enabled: bool


class RestaurantSummary(RestaurantOut):
    role: MemberRole  # the caller's role in this restaurant


class MemberInvite(BaseModel):
    email: EmailStr
    role: MemberRole = MemberRole.STAFF


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: EmailStr
    name: str
    role: MemberRole

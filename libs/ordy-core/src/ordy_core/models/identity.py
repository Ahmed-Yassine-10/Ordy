"""Identity & tenancy models (doc 06 §3.1).

Identity tables (users, oauth_accounts, refresh_tokens, api_keys) are keyed by
user/tenant but are NOT under tenant RLS: auth lookups (login by email, token
refresh, API-key verification) must run before any tenant context exists. Access
is mediated in the app layer. RLS begins at ``restaurants`` and everything that
carries ``restaurant_id``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ordy_core.db.base import Base, TimestampMixin, pk
from ordy_core.enums import MemberRole, RestaurantStatus, UserStatus


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)  # null for OAuth-only
    name: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(8), default="en", nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[UserStatus] = mapped_column(default=UserStatus.ACTIVE, nullable=False)
    mfa_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[RestaurantMember]] = relationship(back_populates="user")


class OAuthAccount(Base, TimestampMixin):
    __tablename__ = "oauth_accounts"
    __table_args__ = (UniqueConstraint("provider", "provider_account_id"),)

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # 'google'
    provider_account_id: Mapped[str] = mapped_column(Text, nullable=False)


class RefreshToken(Base, TimestampMixin):
    """Rotating refresh tokens with reuse detection (doc 08 §2).

    Stored as a hash; ``family_id`` groups a rotation chain so a detected reuse can
    revoke the whole family.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(String(64))


class Restaurant(Base, TimestampMixin):
    """The tenant. RLS root."""

    __tablename__ = "restaurants"

    id: Mapped[uuid.UUID] = pk()
    slug: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RestaurantStatus] = mapped_column(
        default=RestaurantStatus.ONBOARDING, nullable=False
    )
    timezone: Mapped[str] = mapped_column(Text, default="Africa/Tunis", nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="TND", nullable=False)
    default_language: Mapped[str] = mapped_column(String(8), default="fr", nullable=False)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["fr", "en", "ar-TN"], nullable=False
    )
    address: Mapped[dict | None] = mapped_column(JSONB)
    contact: Mapped[dict | None] = mapped_column(JSONB)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    members: Mapped[list[RestaurantMember]] = relationship(back_populates="restaurant")


class RestaurantMember(Base, TimestampMixin):
    __tablename__ = "restaurant_members"

    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("restaurants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[MemberRole] = mapped_column(nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id")
    )

    restaurant: Mapped[Restaurant] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships", foreign_keys=[user_id])


class ApiKey(Base, TimestampMixin):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = pk()
    restaurant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), ForeignKey("users.id"))

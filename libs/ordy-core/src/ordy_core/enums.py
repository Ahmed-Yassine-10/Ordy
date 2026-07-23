"""Closed-set enumerations mirrored as Postgres enums in migrations (doc 06)."""

from __future__ import annotations

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING_VERIFICATION = "pending_verification"


class RestaurantStatus(StrEnum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CHURNED = "churned"


class MemberRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"
    VIEWER = "viewer"

    def rank(self) -> int:
        return {"owner": 3, "manager": 2, "staff": 1, "viewer": 0}[self.value]

    def can_act_as(self, required: MemberRole) -> bool:
        """True if this role satisfies the required minimum (owner ⊇ manager ⊇ …)."""
        return self.rank() >= required.rank()


class MenuStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ProductStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ServiceType(StrEnum):
    DINE_IN = "dine_in"
    PICKUP = "pickup"
    DELIVERY = "delivery"
    RESERVATION = "reservation"


class RiskLevel(StrEnum):
    READ = "read"
    WRITE = "write"
    FINANCIAL = "financial"

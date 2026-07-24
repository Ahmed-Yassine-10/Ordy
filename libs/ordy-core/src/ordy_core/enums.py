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


# ---- Ingestion (doc 04 / doc 06 §3.5) ----


class SourceKind(StrEnum):
    WEBSITE = "website"
    DATABASE = "database"
    GITHUB = "github"
    API_DOC = "api_doc"
    UPLOAD = "upload"


class SourceStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    BROKEN = "broken"


class IngestionTrigger(StrEnum):
    ONBOARDING = "onboarding"
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    CHANGE_DETECTED = "change_detected"


class RunStatus(StrEnum):
    QUEUED = "queued"
    DISCOVERING = "discovering"
    FETCHING = "fetching"
    EXTRACTING = "extracting"
    ANALYZING = "analyzing"
    SYNTHESIZING = "synthesizing"
    AWAITING_REVIEW = "awaiting_review"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    REJECTED = "rejected"

    @property
    def is_terminal(self) -> bool:
        return self in {RunStatus.PUBLISHED, RunStatus.FAILED, RunStatus.REJECTED}


class DocType(StrEnum):
    MENU = "menu"
    HOURS = "hours"
    POLICY = "policy"
    FAQ = "faq"
    PAGE = "page"
    PROMO = "promo"
    CODE_SUMMARY = "code_summary"


class DocStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class MapStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"
    SUPERSEDED = "superseded"


class AdapterKind(StrEnum):
    NATIVE = "native"
    REST = "rest"
    POS = "pos"
    BROWSER = "browser"


# ---- Conversations (doc 06 §3.4) ----


class Channel(StrEnum):
    VOICE_WEB = "voice_web"
    VOICE_PHONE = "voice_phone"
    TEXT_WIDGET = "text_widget"
    SANDBOX = "sandbox"
    DASHBOARD = "dashboard"
    API = "api"


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    ESCALATED = "escalated"
    FAILED = "failed"


class TurnRole(StrEnum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"

"""SQLAlchemy models. Import side-effects register tables on ``Base.metadata``."""

from ordy_core.models.identity import (
    ApiKey,
    OAuthAccount,
    RefreshToken,
    Restaurant,
    RestaurantMember,
    User,
)
from ordy_core.models.knowledge import (
    CapabilityMap,
    IngestionRun,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)
from ordy_core.models.menu import (
    MenuCategory,
    Menu,
    Modifier,
    ModifierGroup,
    Product,
    ProductVariant,
)

__all__ = [
    "ApiKey",
    "CapabilityMap",
    "IngestionRun",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeSource",
    "Menu",
    "MenuCategory",
    "Modifier",
    "ModifierGroup",
    "OAuthAccount",
    "Product",
    "ProductVariant",
    "RefreshToken",
    "Restaurant",
    "RestaurantMember",
    "User",
]

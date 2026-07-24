"""SQLAlchemy models. Import side-effects register tables on ``Base.metadata``."""

from ordy_core.models.identity import (
    ApiKey,
    OAuthAccount,
    RefreshToken,
    Restaurant,
    RestaurantMember,
    User,
)
from ordy_core.models.conversation import (
    AgentConfig,
    Conversation,
    ConversationTurn,
)
from ordy_core.models.knowledge import (
    CapabilityMap,
    IngestionRun,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
)
from ordy_core.models.automation import (
    AutomationRun,
    AutomationWorkflow,
)
from ordy_core.models.orders import (
    Customer,
    DeliveryZoneRow,
    OperatingHours,
    Order,
    OrderEvent,
    OrderItem,
    Reservation,
    UsageRecord,
    WebhookDelivery,
    WebhookEndpoint,
)
from ordy_core.models.tools import (
    ActionExecution,
    RestaurantTool,
    ToolDefinition,
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
    "ActionExecution",
    "AgentConfig",
    "AutomationRun",
    "AutomationWorkflow",
    "ApiKey",
    "Customer",
    "DeliveryZoneRow",
    "CapabilityMap",
    "Conversation",
    "ConversationTurn",
    "IngestionRun",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeSource",
    "Menu",
    "OperatingHours",
    "Order",
    "OrderEvent",
    "OrderItem",
    "MenuCategory",
    "Modifier",
    "ModifierGroup",
    "OAuthAccount",
    "Product",
    "ProductVariant",
    "RefreshToken",
    "Reservation",
    "Restaurant",
    "RestaurantMember",
    "RestaurantTool",
    "ToolDefinition",
    "UsageRecord",
    "User",
    "WebhookDelivery",
    "WebhookEndpoint",
]

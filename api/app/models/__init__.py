"""SQLAlchemy models. Importing this package registers every table on Base.metadata."""
from app.models.base import Base
from app.models.agent import AgentConfig
from app.models.business import Business, Membership
from app.models.customer import Customer
from app.models.menu import (
    Category,
    ModifierGroup,
    ModifierOption,
    Product,
    ProductModifierGroup,
    ProductModifierOptionPrice,
)
from app.models.ops import BusinessHours, DeliveryZone
from app.models.order import Order, OrderItem, OrderStatusHistory
from app.models.user import User
from app.models.whatsapp import WhatsAppConnection, WhatsAppInbox

__all__ = [
    "Base",
    "AgentConfig",
    "User",
    "Business",
    "Membership",
    "Category",
    "Product",
    "ModifierGroup",
    "ModifierOption",
    "ProductModifierGroup",
    "ProductModifierOptionPrice",
    "BusinessHours",
    "DeliveryZone",
    "Customer",
    "Order",
    "OrderItem",
    "OrderStatusHistory",
    "WhatsAppConnection",
    "WhatsAppInbox",
]

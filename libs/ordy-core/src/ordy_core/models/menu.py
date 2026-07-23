"""Menu models (doc 06 §3.2). All are tenant-owned → RLS-protected.

Prices are integer minor units in the restaurant's currency. Variant prices are
absolute (not deltas) for unambiguous server-side pricing (doc 03 §3.4).
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ordy_core.db.base import Base, TenantMixin, TimestampMixin, pk
from ordy_core.enums import MenuStatus, ProductStatus


class Menu(Base, TenantMixin, TimestampMixin):
    __tablename__ = "menus"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text, default="Main menu", nullable=False)
    status: Mapped[MenuStatus] = mapped_column(default=MenuStatus.DRAFT, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)

    categories: Mapped[list[MenuCategory]] = relationship(back_populates="menu")


class MenuCategory(Base, TenantMixin, TimestampMixin):
    __tablename__ = "menu_categories"

    id: Mapped[uuid.UUID] = pk()
    menu_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("menus.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_i18n: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    menu: Mapped[Menu] = relationship(back_populates="categories")
    products: Mapped[list[Product]] = relationship(back_populates="category")


class Product(Base, TenantMixin, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = pk()
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("menu_categories.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_i18n: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    description_i18n: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    price_minor: Mapped[int | None] = mapped_column(BigInteger)  # null when variant-priced
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    allergens: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    availability: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    external_ref: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[ProductStatus] = mapped_column(default=ProductStatus.DRAFT, nullable=False)

    category: Mapped[MenuCategory | None] = relationship(back_populates="products")
    variants: Mapped[list[ProductVariant]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductVariant(Base, TenantMixin, TimestampMixin):
    __tablename__ = "product_variants"

    id: Mapped[uuid.UUID] = pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_i18n: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)  # absolute
    external_ref: Mapped[str | None] = mapped_column(Text)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    product: Mapped[Product] = relationship(back_populates="variants")


class ModifierGroup(Base, TenantMixin, TimestampMixin):
    __tablename__ = "modifier_groups"

    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_i18n: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    min_select: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_select: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    modifiers: Mapped[list[Modifier]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class Modifier(Base, TenantMixin, TimestampMixin):
    __tablename__ = "modifiers"

    id: Mapped[uuid.UUID] = pk()
    group_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("modifier_groups.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_i18n: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    price_delta_minor: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    group: Mapped[ModifierGroup] = relationship(back_populates="modifiers")

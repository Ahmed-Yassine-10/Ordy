"""Assemble AgentDeps for a turn: the brain (rule-based dev / LLM prod) + a retriever
bound to the request's RLS-scoped session (pgvector hybrid search)."""

from __future__ import annotations

import uuid

from ordy_agent.brain import RuleBasedBrain
from ordy_agent.deps import AgentDeps, Retriever
from ordy_agent.tools_runtime import ToolRuntime
from ordy_core.enums import ProductStatus
from ordy_core.models import Product, ProductVariant, Restaurant, RestaurantTool, ToolDefinition
from ordy_rag.models import RetrievedChunk
from ordy_tools.policy import Caps, DeliveryPolicy, PolicyContext, ToolBinding
from ordy_tools.pricing import ProductSnapshot, VariantSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ordy_api.config import get_settings
from ordy_api.embedding import get_embedder
from ordy_api.modules.knowledge.retrieval import hybrid_search


def build_brain():  # type: ignore[no-untyped-def]
    backend = get_settings().agent_brain
    if backend == "llm":
        raise NotImplementedError("LLM brain lands with the model-router completion client")
    return RuleBasedBrain()


def make_retriever(session: AsyncSession, restaurant_id: uuid.UUID) -> Retriever:
    embedder = get_embedder()

    async def retrieve(query: str, k: int) -> list[RetrievedChunk]:
        hits = await hybrid_search(session, restaurant_id, query, embedder, k=k)
        return [
            RetrievedChunk(
                chunk_id=h["chunk_id"],
                content=h["content"],
                score=h["score"],
                document_id=h["document_id"],
                provenance=h["provenance"],
                language=h["language"],
            )
            for h in hits
        ]

    return retrieve


async def build_policy_context(
    session: AsyncSession, restaurant_id: uuid.UUID, *, channel: str
) -> PolicyContext:
    """Resolve the gate's inputs from the database — tool bindings, the published menu
    snapshot, service hours, delivery policy, caps. The model supplies none of this.

    Hours/delivery currently come from ``restaurants.settings``; the dedicated
    ``operating_hours`` / ``delivery_zones`` tables land with orders in Phase 7.
    """
    restaurant = await session.get(Restaurant, restaurant_id)
    settings = dict(restaurant.settings or {}) if restaurant else {}
    currency = restaurant.currency if restaurant else "TND"

    rows = await session.execute(
        select(RestaurantTool, ToolDefinition).join(
            ToolDefinition, RestaurantTool.tool_definition_id == ToolDefinition.id
        ).where(RestaurantTool.restaurant_id == restaurant_id)
    )
    bindings = {
        definition.key: ToolBinding(
            tool_key=definition.key,
            enabled=binding.enabled,
            adapter=binding.adapter,
            channels=list(binding.channels),
            caps=dict(binding.caps),
        )
        for binding, definition in rows
    }

    products = list(
        await session.scalars(
            select(Product).where(
                Product.restaurant_id == restaurant_id,
                Product.status == ProductStatus.PUBLISHED,
                Product.deleted_at.is_(None),
            )
        )
    )
    variants = list(
        await session.scalars(
            select(ProductVariant).where(ProductVariant.restaurant_id == restaurant_id)
        )
    )
    by_product: dict[uuid.UUID, list[ProductVariant]] = {}
    for variant in variants:
        by_product.setdefault(variant.product_id, []).append(variant)

    menu = {
        str(p.id): ProductSnapshot(
            product_id=str(p.id),
            name=p.name,
            currency=p.currency,
            price_minor=p.price_minor,
            is_available=p.is_available,
            variants={
                str(v.id): VariantSnapshot(str(v.id), v.name, v.price_minor, v.is_available)
                for v in by_product.get(p.id, [])
            },
        )
        for p in products
    }

    service_settings = settings.get("service_open") or {}
    service_open = {
        service: bool(service_settings.get(service, True))
        for service in ("pickup", "delivery", "dine_in", "reservation")
    }
    delivery_settings = settings.get("delivery") or {}

    return PolicyContext(
        channel=channel,
        currency=currency,
        bindings=bindings,
        menu=menu,
        service_open=service_open,
        delivery=DeliveryPolicy(
            in_zone=bool(delivery_settings.get("in_zone", True)),
            min_order_minor=int(delivery_settings.get("min_order_minor", 0)),
            fee_minor=int(delivery_settings.get("fee_minor", 0)),
        ),
        caps=Caps().tightened_by(settings.get("caps") or {}),
    )


def build_deps(
    session: AsyncSession,
    restaurant_id: uuid.UUID,
    persona: dict,
    *,
    tools: ToolRuntime | None = None,
) -> AgentDeps:
    return AgentDeps(
        brain=build_brain(),
        retrieve=make_retriever(session, restaurant_id),
        persona=persona,
        tools=tools,
    )

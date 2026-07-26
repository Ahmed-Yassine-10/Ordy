"""Concrete Action Provider integrations.

Each module here adapts a real restaurant backend to Ordy's ``ExecutorAdapter`` contract
(``execute(tool_key, args, *, idempotency_key) -> dict``). The adapters are pure and
transport-agnostic — they depend on a small ``RestTransport`` protocol so they stay
unit-testable with a fake, while production drives them over HTTP. Endpoints come from an
approved ``ordy.config.json`` Capability Map, loaded by :mod:`config_loader`.
"""

from ordy_tools.providers.alostedh import (
    AlOstedhAdapter,
    CustomerContext,
    RestTransport,
    adapter_from_config,
    menu_snapshot,
    to_major,
    to_minor,
)
from ordy_tools.providers.config_loader import (
    ConsentError,
    OrdyConfig,
    RouteBinding,
    load_config,
)

__all__ = [
    "AlOstedhAdapter",
    "ConsentError",
    "CustomerContext",
    "OrdyConfig",
    "RestTransport",
    "RouteBinding",
    "adapter_from_config",
    "load_config",
    "menu_snapshot",
    "to_major",
    "to_minor",
]

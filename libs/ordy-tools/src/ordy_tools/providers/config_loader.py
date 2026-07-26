"""Load an ``ordy.config.json`` (produced by @ordy/analyze) into runtime route bindings.

This is the missing link between onboarding and execution: the CLI writes a Capability Map
the owner approves; this reads it back and hands the executor a per-action
(method, path, auth) binding. Consent is enforced here — a config whose owner never approved
must not drive a single write against the restaurant's system.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


class ConsentError(RuntimeError):
    """Raised when a config that has not been approved is used to place actions."""


@dataclass(slots=True, frozen=True)
class RouteBinding:
    action: str
    method: str
    path: str
    auth_required: bool
    confidence: float = 0.0
    needs_review: bool = False


@dataclass(slots=True)
class OrdyConfig:
    restaurant_name: str
    currency: str
    consent_approved: bool
    consent_by: str | None
    routes: dict[str, RouteBinding] = field(default_factory=dict)  # action -> binding (rest only)
    native_actions: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def rest_binding(self, action: str) -> RouteBinding | None:
        return self.routes.get(action)

    def require_consent(self) -> None:
        """Guard to call before any state-changing execution driven by this config."""
        if not self.consent_approved:
            raise ConsentError(
                f"ordy.config.json for '{self.restaurant_name}' is not approved — "
                "run `ordy-analyze --approve \"<name>\"` first."
            )


def load_config(source: str | Path | dict) -> OrdyConfig:
    """Parse an ordy.config.json path (or an already-parsed dict) into an OrdyConfig."""
    if isinstance(source, dict):
        data = source
    else:
        path = Path(source)
        if path.is_dir():
            path = path / "ordy.config.json"
        data = json.loads(path.read_text(encoding="utf-8"))

    routes: dict[str, RouteBinding] = {}
    native: list[str] = []
    for cap in data.get("capabilities", []):
        action = cap.get("action", "")
        if cap.get("binding") == "rest" and cap.get("method") and cap.get("path"):
            routes[action] = RouteBinding(
                action=action,
                method=str(cap["method"]).upper(),
                path=str(cap["path"]),
                auth_required=cap.get("auth") == "bearer",
                confidence=float(cap.get("confidence", 0.0)),
                needs_review=bool(cap.get("needsReview", False)),
            )
        else:
            native.append(action)

    restaurant = data.get("restaurant", {})
    consent = data.get("consent", {})
    return OrdyConfig(
        restaurant_name=str(restaurant.get("name", "restaurant")),
        currency=str(restaurant.get("currency", "TND")),
        consent_approved=bool(consent.get("approved", False)),
        consent_by=consent.get("approvedBy"),
        routes=routes,
        native_actions=native,
        raw=data,
    )

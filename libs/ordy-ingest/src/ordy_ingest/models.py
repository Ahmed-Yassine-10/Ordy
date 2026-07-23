"""Pipeline data structures. Drafts serialize to JSONB for the review UI (doc 04 §2.7)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Provenance:
    """Where a fact came from — powers the review UI and the injection boundary (doc 04 §4)."""

    source_url: str
    method: str  # 'json-ld' | 'heuristic' | 'llm' | 'openapi' | 'manual'
    snippet: str = ""


@dataclass(slots=True)
class VariantDraft:
    name: str
    price_minor: int


@dataclass(slots=True)
class MenuItemDraft:
    name: str
    currency: str
    description: str | None = None
    category: str | None = None
    price_minor: int | None = None
    variants: list[VariantDraft] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)
    confidence: float = 1.0
    provenance: Provenance | None = None
    # True when the extractor is unsure (e.g. "from 12 TND") — forces reviewer attention.
    needs_review: bool = False

    def key(self) -> str:
        return _normalize_name(self.name)


@dataclass(slots=True)
class HoursDraft:
    service: str  # dine_in | pickup | delivery | reservation
    day_of_week: int  # 0=Mon … 6=Sun
    opens: str  # 'HH:MM'
    closes: str
    provenance: Provenance | None = None


@dataclass(slots=True)
class PolicyDraft:
    kind: str  # delivery | cancellation | payment | dietary | other
    text: str
    provenance: Provenance | None = None


@dataclass(slots=True)
class PageContent:
    url: str
    html: str = ""
    text: str = ""
    status: int = 200
    kind: str = "html"  # html | json | pdf


@dataclass(slots=True)
class ExtractionResult:
    items: list[MenuItemDraft] = field(default_factory=list)
    hours: list[HoursDraft] = field(default_factory=list)
    policies: list[PolicyDraft] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CapabilityCandidate:
    action: str
    feasible: bool
    adapter: str  # native | rest | pos | browser
    confidence: float = 0.0
    binding: dict = field(default_factory=dict)
    reason: str | None = None
    evidence: list[dict] = field(default_factory=list)


def to_jsonable(obj: object) -> object:
    """Recursively convert dataclasses to plain dict/list for JSONB storage."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    return obj


def _normalize_name(name: str) -> str:
    return " ".join(name.lower().split())

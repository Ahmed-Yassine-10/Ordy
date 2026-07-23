"""ordy-ingest — the restaurant-intelligence pipeline (doc 04).

The pure stages (JSON-LD extraction, OpenAPI analysis, synthesis, diff) depend only
on the standard library + ordy-core, so they are unit-testable without a browser or
an LLM. Real crawling/LLM backends live behind ports in ``fetch`` / ``extract``.
"""

from ordy_ingest.analyze import analyze_openapi, build_capability_map
from ordy_ingest.diff import Change, detect_menu_changes
from ordy_ingest.extract import extract_jsonld
from ordy_ingest.models import (
    CapabilityCandidate,
    ExtractionResult,
    HoursDraft,
    MenuItemDraft,
    PageContent,
    PolicyDraft,
    Provenance,
    VariantDraft,
)
from ordy_ingest.orchestrator import IngestionOutput, run_pipeline
from ordy_ingest.synthesize import DraftBundle, synthesize

__all__ = [
    "CapabilityCandidate",
    "Change",
    "DraftBundle",
    "ExtractionResult",
    "HoursDraft",
    "IngestionOutput",
    "MenuItemDraft",
    "PageContent",
    "PolicyDraft",
    "Provenance",
    "VariantDraft",
    "analyze_openapi",
    "build_capability_map",
    "detect_menu_changes",
    "extract_jsonld",
    "run_pipeline",
    "synthesize",
]

"""Pipeline orchestration (doc 04 §2). Pure over its ports so it runs synchronously
in tests and under Celery in the worker with identical behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ordy_ingest.analyze import analyze_openapi, build_capability_map
from ordy_ingest.extract import LLMExtractor, NullLLMExtractor, extract_jsonld
from ordy_ingest.fetch import Fetcher
from ordy_ingest.models import ExtractionResult
from ordy_ingest.synthesize import DraftBundle, synthesize


@dataclass(slots=True)
class IngestionOutput:
    bundle: DraftBundle
    capability_map: dict
    pages_fetched: int = 0
    warnings: list[str] = field(default_factory=list)


def _parse_spec(text: str) -> dict | None:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValueError):
        pass
    try:  # optional YAML support
        import yaml  # type: ignore

        data = yaml.safe_load(text)
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover  (noqa: BLE001)
        return None


def run_pipeline(
    *,
    kind: str,
    config: dict,
    fetcher: Fetcher,
    currency: str = "TND",
    llm: LLMExtractor | None = None,
    max_pages: int = 50,
) -> IngestionOutput:
    """Run the pipeline for one source. Returns drafts + a Capability Map.

    ``kind`` ∈ {website, api_doc, database, github, upload}. Website yields knowledge
    (+ native capabilities); api_doc yields REST capabilities.
    """
    llm = llm or NullLLMExtractor()
    warnings: list[str] = []

    if kind == "website":
        base_url = config["url"]
        pages = fetcher.crawl(base_url, max_pages=max_pages)
        results: list[ExtractionResult] = []
        for page in pages:
            if page.status != 200 or page.kind != "html":
                continue
            res = extract_jsonld(page, currency)
            if not res.items:  # nothing structured — let the LLM try the text
                res = _merge_extraction(res, llm.extract(text=page.text or page.html, url=page.url, currency=currency))
            results.append(res)
        bundle = synthesize(results)
        if not bundle.items:
            warnings.append("no menu items extracted — site may need manual entry or an upload")
        cap = build_capability_map([], coverage=bundle.coverage)
        return IngestionOutput(bundle=bundle, capability_map=cap, pages_fetched=len(pages), warnings=warnings)

    if kind == "api_doc":
        page = fetcher.fetch(config["url"])
        spec = _parse_spec(page.text or page.html)
        if spec is None:
            warnings.append("could not parse API document as OpenAPI JSON/YAML")
            return IngestionOutput(bundle=synthesize([]), capability_map=build_capability_map([], coverage={}), warnings=warnings)
        candidates = analyze_openapi(spec)
        cap = build_capability_map(candidates, coverage={"source": "openapi"})
        return IngestionOutput(bundle=synthesize([]), capability_map=cap, pages_fetched=1, warnings=warnings)

    # database / github / upload — capability-map placeholder + guidance for the reviewer.
    warnings.append(f"source kind '{kind}' yields native capabilities only in Phase 3")
    return IngestionOutput(
        bundle=synthesize([]),
        capability_map=build_capability_map([], coverage={"source": kind}),
        warnings=warnings,
    )


def _merge_extraction(a: ExtractionResult, b: ExtractionResult) -> ExtractionResult:
    a.items.extend(b.items)
    a.hours.extend(b.hours)
    a.policies.extend(b.policies)
    a.warnings.extend(b.warnings)
    return a

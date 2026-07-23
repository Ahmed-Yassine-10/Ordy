"""Fetcher selection per source kind (doc 04 §2.1)."""

from __future__ import annotations

from ordy_ingest.fetch import Fetcher, StaticFetcher


def build_fetcher(kind: str, config: dict) -> Fetcher:
    # Phase 3 baseline: HTTP fetcher for websites and API docs. JS-heavy sites are
    # upgraded to PlaywrightFetcher (renders + snapshots) as it lands.
    if kind in {"website", "api_doc"}:
        return StaticFetcher()
    raise NotImplementedError(f"no fetcher for source kind '{kind}' yet")

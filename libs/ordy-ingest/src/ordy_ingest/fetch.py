"""Fetch ports (doc 04 §2.1–2.2).

``FixtureFetcher`` (in-memory) drives tests. ``StaticFetcher`` (httpx, optional)
fetches API docs and simple pages. The production website crawler is
``PlaywrightFetcher`` — it renders JS-heavy sites and snapshots each page; it lives
behind the same port so the pipeline is agnostic to how bytes arrive.
"""

from __future__ import annotations

import re
from typing import Protocol

from ordy_ingest.models import PageContent

_HREF_RE = re.compile(r'href=["\']([^"\'#]+)["\']', re.IGNORECASE)


class Fetcher(Protocol):
    def fetch(self, url: str) -> PageContent: ...
    def crawl(self, base_url: str, *, max_pages: int = 50) -> list[PageContent]: ...


class FixtureFetcher:
    """Serves a fixed set of pages. For tests and deterministic replays."""

    def __init__(self, pages: dict[str, PageContent]) -> None:
        self._pages = pages

    def fetch(self, url: str) -> PageContent:
        if url not in self._pages:
            return PageContent(url=url, status=404)
        return self._pages[url]

    def crawl(self, base_url: str, *, max_pages: int = 50) -> list[PageContent]:
        return list(self._pages.values())[:max_pages]


class StaticFetcher:
    """httpx-backed fetcher for non-JS pages and API docs. Requires the 'crawl' extra."""

    USER_AGENT = "OrdyBot/1.0 (+https://ordy.ai/bot)"

    def __init__(self, timeout: float = 15.0) -> None:
        try:
            import httpx  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("StaticFetcher needs the 'crawl' extra (httpx)") from exc
        self._timeout = timeout

    def fetch(self, url: str) -> PageContent:
        import httpx

        resp = httpx.get(
            url, timeout=self._timeout, follow_redirects=True,
            headers={"User-Agent": self.USER_AGENT},
        )
        ctype = resp.headers.get("content-type", "")
        kind = "json" if "json" in ctype else "html"
        return PageContent(url=str(resp.url), html=resp.text, text=resp.text, status=resp.status_code, kind=kind)

    def crawl(self, base_url: str, *, max_pages: int = 50) -> list[PageContent]:
        """Shallow, same-host BFS (depth 1). Real crawling uses PlaywrightFetcher."""
        from urllib.parse import urljoin, urlparse

        root = self.fetch(base_url)
        pages = [root]
        host = urlparse(base_url).netloc
        seen = {base_url}
        for href in _HREF_RE.findall(root.html)[: max_pages * 3]:
            target = urljoin(base_url, href)
            if urlparse(target).netloc != host or target in seen:
                continue
            seen.add(target)
            pages.append(self.fetch(target))
            if len(pages) >= max_pages:
                break
        return pages


class PlaywrightFetcher:
    """Production website crawler (renders JS, snapshots pages). Requires the 'crawl'
    extra + ``playwright install``. Implemented in Phase 3.x for the worker."""

    def __init__(self) -> None:  # pragma: no cover
        raise NotImplementedError(
            "PlaywrightFetcher is wired in the worker (services/workers); "
            "install the 'crawl' extra and run `playwright install chromium`."
        )

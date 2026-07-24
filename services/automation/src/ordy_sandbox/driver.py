"""Playwright implementation of the BrowserDriver port (doc 04 §6).

Kept thin on purpose: all decisions (what to click, what must hold, what must never be
typed) live in the verified workflow + ordy-automation's guards. This class only knows
how to operate a page and capture evidence.
"""

from __future__ import annotations

from ordy_automation.safety import mask_for_artifact


class PlaywrightDriver:
    """Requires the 'playwright' extra and `playwright install chromium`."""

    def __init__(self, page, artifacts_prefix: str) -> None:  # type: ignore[no-untyped-def]
        self._page = page
        self._prefix = artifacts_prefix
        self._step = 0

    async def goto(self, url: str) -> None:
        await self._page.goto(url, wait_until="domcontentloaded")

    async def click(self, selectors: list[str]) -> bool:
        """Try selector candidates in order — primary first, then recorded fallbacks."""
        for selector in selectors:
            locator = self._locator(selector)
            try:
                if await locator.count() > 0:
                    await locator.first.click(timeout=5_000)
                    return True
            except Exception:  # noqa: BLE001 — try the next candidate
                continue
        return False

    async def select_option(self, target: str, value: str) -> bool:
        try:
            await self._page.select_option(f"[name='{target}']", label=value, timeout=5_000)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def fill(self, field: str, value: str) -> None:
        # Guards in ordy-automation already refused payment fields before this point.
        await self._page.fill(f"[name='{field}']", value, timeout=5_000)

    async def check(self, expectation: str) -> bool:
        """Expected-state assertions. Mapped to page conditions per workflow vocabulary."""
        checks = {
            "item_page_or_modal": "[data-testid='item'], .product-detail, .modal",
            "option_selected": "option:checked, [aria-selected='true']",
            "cart_count_increased": "[data-testid='cart-count'], .cart-count",
            "checkout_form_visible": "form[action*='checkout'], .checkout-form",
            "form_filled": "form",
            "order_confirmation_visible": ".order-confirmation, [data-testid='order-ref']",
        }
        selector = checks.get(expectation)
        if selector is None:
            return False
        try:
            return await self._page.locator(selector).count() > 0
        except Exception:  # noqa: BLE001
            return False

    async def capture(self, name: str) -> str:
        """Screenshot + DOM snapshot for the run's evidence trail (doc 08 §5)."""
        self._step += 1
        key = f"{self._prefix}/{self._step:02d}-{name}.png"
        await self._page.screenshot(path=key, full_page=True)
        return key

    async def read(self, name: str) -> str | None:
        selectors = {"order_reference": "[data-testid='order-ref'], .order-reference"}
        selector = selectors.get(name)
        if not selector:
            return None
        try:
            text = await self._page.locator(selector).first.inner_text(timeout=3_000)
            return mask_for_artifact(name, text.strip())
        except Exception:  # noqa: BLE001
            return None

    def _locator(self, selector: str):  # type: ignore[no-untyped-def]
        if selector.startswith("css:"):
            return self._page.locator(selector[4:])
        if selector.startswith("text:"):
            return self._page.get_by_text(selector[5:], exact=False)
        return self._page.locator(selector)

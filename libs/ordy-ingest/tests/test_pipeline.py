"""Pure-pipeline tests — no browser, no LLM, no DB (stdlib + ordy-core only)."""

from __future__ import annotations

import copy

from ordy_ingest.analyze import analyze_openapi, build_capability_map
from ordy_ingest.diff import detect_menu_changes
from ordy_ingest.extract import extract_jsonld
from ordy_ingest.fetch import FixtureFetcher
from ordy_ingest.models import PageContent
from ordy_ingest.orchestrator import run_pipeline
from ordy_ingest.prices import parse_price
from ordy_ingest.synthesize import synthesize

MENU_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Menu","hasMenuSection":[
  {"@type":"MenuSection","name":"Pizzas","hasMenuItem":[
    {"@type":"MenuItem","name":"Pizza Pepperoni","description":"Spicy",
     "offers":[{"@type":"Offer","name":"Medium","price":"24.000","priceCurrency":"TND"},
               {"@type":"Offer","name":"Large","price":"32.000","priceCurrency":"TND"}]},
    {"@type":"MenuItem","name":"Margherita","offers":{"@type":"Offer","price":"18.5","priceCurrency":"TND"}}
  ]}
]}
</script></head><body>livraison</body></html>
"""


def _page() -> PageContent:
    return PageContent(url="https://pizzarustica.tn/menu", html=MENU_HTML, text="livraison")


def test_parse_price_is_exponent_aware() -> None:
    assert parse_price("32.000", "TND") == 32_000
    assert parse_price(32, "TND") == 32_000
    assert parse_price("18.5", "TND") == 18_500
    assert parse_price("12.50", "EUR") == 1_250
    assert parse_price("not a price", "TND") is None


def test_jsonld_extraction_with_variants_and_category() -> None:
    res = extract_jsonld(_page(), "TND")
    assert len(res.items) == 2
    pep = next(i for i in res.items if "pepperoni" in i.name.lower())
    assert [v.price_minor for v in pep.variants] == [24_000, 32_000]
    marg = next(i for i in res.items if "margh" in i.name.lower())
    assert marg.price_minor == 18_500
    assert marg.category == "Pizzas"


def test_synthesize_coverage_and_stats() -> None:
    bundle = synthesize([extract_jsonld(_page(), "TND")])
    assert bundle.stats["items_extracted"] == 2
    assert bundle.coverage["categories"] == 1


def test_openapi_capability_detection() -> None:
    spec = {
        "paths": {
            "/orders": {"post": {"operationId": "createOrder", "summary": "Place an order"}},
            "/orders/{id}": {"get": {"summary": "Order status"}},
            "/reservations": {"post": {"summary": "Book a table"}},
            "/menu/availability": {"get": {"summary": "Check availability"}},
        }
    }
    got = {c.action: c.adapter for c in analyze_openapi(spec)}
    assert got["create_order"] == "rest"
    assert "make_reservation" in got and "check_availability" in got

    cap = build_capability_map(analyze_openapi(spec), coverage={})
    by_action = {c["action"]: c for c in cap["capabilities"]}
    assert by_action["create_order"]["adapter"] == "rest"
    # actions with no endpoint fall back to native, always feasible
    assert by_action["request_human_handoff"]["adapter"] == "native"
    assert len(cap["capabilities"]) == 11


def test_price_change_routes_to_review() -> None:
    old = extract_jsonld(_page(), "TND").items
    new = copy.deepcopy(old)
    new[1].price_minor = 20_000
    changes = detect_menu_changes(old, new)
    price_changes = [c for c in changes if c.kind == "price_changed"]
    assert price_changes and price_changes[0].requires_review


def test_orchestrator_website_end_to_end() -> None:
    page = _page()
    out = run_pipeline(
        kind="website",
        config={"url": page.url},
        fetcher=FixtureFetcher({page.url: page}),
        currency="TND",
    )
    assert out.bundle.stats["items_extracted"] == 2
    assert len(out.capability_map["capabilities"]) == 11
    assert out.pages_fetched == 1

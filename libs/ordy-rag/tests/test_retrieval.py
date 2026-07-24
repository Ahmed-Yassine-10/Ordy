"""RAG unit + retrieval-eval tests — no DB, no provider (stdlib + ordy-core)."""

from __future__ import annotations

from ordy_rag.chunk import chunk_markdown
from ordy_rag.embed import HashingEmbedder
from ordy_rag.fuse import reciprocal_rank_fusion
from ordy_rag.ground import check_grounding
from ordy_rag.models import RetrievedChunk
from ordy_rag.retrieve import hybrid_retrieve
from ordy_rag.store import InMemoryVectorStore

MENU_MD = """# Menu
## Pizzas
Pizza Pepperoni Medium 24000 Large 32000 spicy pepperoni mozzarella.
Margherita 18500 tomato mozzarella basil vegetarian sans viande.
## Boissons
Coca cola 3000 boisson. Eau minerale 1500 water.
"""


def test_chunk_markdown_is_heading_aware() -> None:
    chunks = chunk_markdown(MENU_MD, target_tokens=10, overlap=2)
    assert len(chunks) >= 3
    assert {c.headings_path for c in chunks} >= {"Pizzas", "Boissons"}


def test_rrf_orders_by_fused_rank() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["c", "a", "d"]])
    ids = [f[0] for f in fused]
    assert ids[0] in ("a", "c")
    assert set(ids) == {"a", "b", "c", "d"}


def _build_store() -> tuple[InMemoryVectorStore, HashingEmbedder]:
    emb = HashingEmbedder(dim=512)
    store = InMemoryVectorStore()
    docs = {
        "pep": "Pizza Pepperoni Medium 24000 Large 32000 spicy pepperoni mozzarella",
        "marg": "Margherita 18500 tomato mozzarella basil vegetarian sans viande",
        "coca": "Coca cola 3000 boisson",
        "eau": "Eau minerale 1500 water",
    }
    for cid, text in docs.items():
        store.add(cid, emb.embed([text])[0], text, document_id="doc1", provenance={"source_url": "https://x/menu"})
    return store, emb


def test_hybrid_retrieval_hit_at_3() -> None:
    store, emb = _build_store()
    evalset = [
        ("how much is the pepperoni pizza", "pep"),
        ("vegetarian options", "marg"),
        ("price of water", "eau"),
        ("do you have coca cola", "coca"),
    ]
    hits = sum(
        1 for q, expected in evalset if expected in [r.chunk_id for r in hybrid_retrieve(store, q, emb, k=3)]
    )
    assert hits / len(evalset) >= 0.95


def test_provenance_travels_with_results() -> None:
    store, emb = _build_store()
    top = hybrid_retrieve(store, "pepperoni", emb, k=1)[0]
    assert top.provenance.get("source_url") == "https://x/menu"


def test_grounding_flags_unsupported_numbers() -> None:
    chunks = [RetrievedChunk("pep", "Large pepperoni 32000", 1.0)]
    assert check_grounding("The large pepperoni is 32000.", chunks).grounded
    bad = check_grounding("It is 99999 dinars.", chunks)
    assert not bad.grounded and "99999" in bad.unsupported_numbers

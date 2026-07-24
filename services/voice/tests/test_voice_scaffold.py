"""Pure voice-layer tests: pipeline selection + menu lexicon (no audio stack)."""

from __future__ import annotations

from ordy_voice.lexicon import compile_lexicon
from ordy_voice.pipelines import PipelineMode, select_pipeline


def test_derja_forces_modular_pipeline() -> None:
    assert select_pipeline(language="ar-TN") == PipelineMode.MODULAR
    assert select_pipeline(language="en") == PipelineMode.REALTIME
    assert select_pipeline(language="fr", cost_sensitive=True) == PipelineMode.MODULAR
    assert select_pipeline(language="fr", realtime_available=False) == PipelineMode.MODULAR


def test_lexicon_includes_item_names_and_base_terms() -> None:
    lex = compile_lexicon(["Pizza Pepperoni", "Makloub Kafteji"])
    lowered = [b.lower() for b in lex.boost]
    assert "pizza pepperoni" in lowered  # full name boosted
    assert "pepperoni" in lowered  # salient word boosted
    assert "harissa" in lowered  # base Tunisian term
    # stopwords are not boosted as standalone terms
    assert "de" not in lowered

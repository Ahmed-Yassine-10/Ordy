"""ordy-voice — LiveKit agent workers (doc 05).

Phase 5 lands the structure: the STT/TTS/transport ports, the two pipeline modes, the
menu-derived lexicon compiler (pure), and the worker skeleton. Live audio wiring +
vendor selection follow the Derja benchmark spike (doc 05 §6).
"""

from ordy_voice.lexicon import Lexicon, compile_lexicon
from ordy_voice.pipelines import PipelineMode, select_pipeline

__all__ = ["Lexicon", "PipelineMode", "compile_lexicon", "select_pipeline"]

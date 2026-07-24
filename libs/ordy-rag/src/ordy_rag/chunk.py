"""Heading-aware chunking (doc 04 §2.8): ~target-token windows with overlap, keeping
the section heading path on each chunk so retrieval and provenance stay meaningful."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ChunkDraft:
    index: int
    content: str
    token_count: int
    headings_path: str = ""


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading = ""
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            if body:
                sections.append((heading, "\n".join(body)))
                body = []
            heading = stripped.lstrip("#").strip()
        else:
            body.append(line)
    if body:
        sections.append((heading, "\n".join(body)))
    return sections


def chunk_markdown(
    text: str, *, target_tokens: int = 200, overlap: int = 30
) -> list[ChunkDraft]:
    """Split markdown into overlapping, heading-prefixed chunks.

    Token count is approximated by word count — adequate for the small, mostly-list
    restaurant corpora. Empty sections are skipped.
    """
    if target_tokens <= 0:
        raise ValueError("target_tokens must be positive")
    step = max(1, target_tokens - overlap)
    chunks: list[ChunkDraft] = []

    for heading, body in _split_sections(text):
        words = body.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            window = words[start : start + target_tokens]
            prefix = f"{heading}\n" if heading else ""
            chunks.append(
                ChunkDraft(
                    index=len(chunks),
                    content=prefix + " ".join(window),
                    token_count=len(window),
                    headings_path=heading,
                )
            )
            if start + target_tokens >= len(words):
                break
            start += step
    return chunks

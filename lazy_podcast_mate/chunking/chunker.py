"""Semantic chunker: paragraphs first, then sentences, hard-split as last resort."""

from __future__ import annotations

import logging

from .models import TextChunk
from .sentences import split_sentences

log = logging.getLogger(__name__)


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _pack_sentences(sentences: list[str], max_chars: int) -> list[str]:
    """Greedy-pack sentences into chunks no longer than `max_chars`."""
    out: list[str] = []
    current: list[str] = []
    current_len = 0

    for sentence in sentences:
        sep = 1 if current else 0  # single space when joining
        if len(sentence) > max_chars:
            if current:
                out.append(" ".join(current))
                current = []
                current_len = 0
            log.warning(
                "sentence of %d chars exceeds max_chars=%d; hard-splitting",
                len(sentence),
                max_chars,
            )
            for i in range(0, len(sentence), max_chars):
                out.append(sentence[i : i + max_chars])
            continue

        if current_len + sep + len(sentence) > max_chars:
            out.append(" ".join(current))
            current = [sentence]
            current_len = len(sentence)
        else:
            current.append(sentence)
            current_len += sep + len(sentence)

    if current:
        out.append(" ".join(current))
    return out


def chunk_script(script: str, *, max_chars: int) -> list[TextChunk]:
    """Produce ordered, indexed chunks suitable for TTS.

    Strategy: split paragraphs first. Each paragraph that fits becomes one
    chunk; paragraphs that exceed `max_chars` are split into sentences and
    packed back up to the limit. A single sentence larger than the limit
    triggers a hard character split (and a warning).
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be > 0")

    chunks: list[str] = []
    for paragraph in _split_paragraphs(script):
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue
        sentences = split_sentences(paragraph)
        chunks.extend(_pack_sentences(sentences, max_chars))

    return [TextChunk.make(index=i, text=c) for i, c in enumerate(chunks)]

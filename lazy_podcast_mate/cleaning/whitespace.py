"""Whitespace normalisation and sentence-boundary repair."""

from __future__ import annotations

import re

_SENTENCE_TERMINATORS = ".!?;。！？；…"
_OPENING_QUOTES = '"\'“‘（(「『'
_CLOSING_QUOTES = '"\'”’）)」』'
_MULTIPLE_BLANK_LINES_RE = re.compile(r"\n{3,}")
_TRAILING_SPACES_RE = re.compile(r"[ \t]+(\n)")
_INLINE_WHITESPACE_RE = re.compile(r"[ \t]{2,}")


def _repair_mid_sentence_breaks(text: str) -> str:
    lines = text.split("\n")
    out: list[str] = []
    buffer: list[str] = []

    def flush_buffer() -> None:
        if buffer:
            out.append(" ".join(s.strip() for s in buffer).strip())
            buffer.clear()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            flush_buffer()
            out.append("")
            continue

        if not buffer:
            buffer.append(stripped)
            continue

        # Decide whether the previous buffered line terminates a sentence.
        prev = buffer[-1].rstrip()
        terminated = bool(prev) and (
            prev[-1] in _SENTENCE_TERMINATORS
            or (prev[-1] in _CLOSING_QUOTES and len(prev) > 1 and prev[-2] in _SENTENCE_TERMINATORS)
        )
        if terminated:
            flush_buffer()
            buffer.append(stripped)
        else:
            buffer.append(stripped)

    flush_buffer()
    return "\n".join(out)


def normalise_whitespace(text: str) -> str:
    """Repair mid-sentence breaks, collapse whitespace, trim blank lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_SPACES_RE.sub(r"\1", text)
    text = _repair_mid_sentence_breaks(text)
    text = _INLINE_WHITESPACE_RE.sub(" ", text)
    text = _MULTIPLE_BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()

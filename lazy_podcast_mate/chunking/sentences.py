"""Sentence splitter tuned for both Chinese and English punctuation.

Splits a paragraph into sentences, preserving terminators.
"""

from __future__ import annotations

import re

_SENTENCE_TERMINATORS = ".!?;。！？；…"
# Match: run of non-terminators + one-or-more terminators + optional closing quotes.
_SENTENCE_RE = re.compile(
    r"[^" + re.escape(_SENTENCE_TERMINATORS) + r"]+"
    r"[" + re.escape(_SENTENCE_TERMINATORS) + r"]+"
    r"[\"'”’）)」』]*",
    flags=re.DOTALL,
)


def split_sentences(paragraph: str) -> list[str]:
    """Return the list of sentences found in `paragraph`, in order.

    Any trailing fragment that doesn't end with a terminator is returned as
    its own "sentence" so no content is dropped.
    """
    if not paragraph:
        return []

    sentences: list[str] = []
    last_end = 0
    for match in _SENTENCE_RE.finditer(paragraph):
        start, end = match.span()
        if start > last_end:
            # Leading whitespace / content between matches — absorb into next.
            leading = paragraph[last_end:start]
            if leading.strip():
                sentences.append(leading.strip())
        sentences.append(match.group(0).strip())
        last_end = end

    if last_end < len(paragraph):
        tail = paragraph[last_end:].strip()
        if tail:
            sentences.append(tail)

    return [s for s in sentences if s]

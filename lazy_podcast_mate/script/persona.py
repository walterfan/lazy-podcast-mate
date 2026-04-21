"""Post-processing to enforce persona rules after LLM output.

The prompt is the primary defence; this is a belt-and-braces pass that
guarantees invariants regardless of prompt adherence.
"""

from __future__ import annotations

import re

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U00002600-\U000027BF"
    "\U0001FA70-\U0001FAFF"
    "\U0001F000-\U0001F0FF"
    "]",
    flags=re.UNICODE,
)
_EXCLAMATION_RUN_RE = re.compile(r"[!！]{2,}")


def enforce_persona(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _EXCLAMATION_RUN_RE.sub(lambda m: m.group(0)[0], text)
    return text

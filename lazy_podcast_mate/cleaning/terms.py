"""Term-dictionary substitution."""

from __future__ import annotations

import re
from typing import Iterable

from ..config.schema import TermEntry


def _compile_entry(entry: TermEntry) -> tuple[re.Pattern[str], str]:
    pattern = re.escape(entry.from_)
    if entry.word_boundary:
        # Use lookarounds so we also get boundaries around CJK where \b doesn't
        # trigger. `[^\w]` plus string anchors covers ASCII cleanly; for CJK we
        # accept any non-identifier boundary.
        pattern = rf"(?<![\w]){pattern}(?![\w])"
    flags = 0 if entry.case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags), entry.to


def apply_terms(text: str, entries: Iterable[TermEntry]) -> str:
    for entry in entries:
        regex, replacement = _compile_entry(entry)
        text = regex.sub(replacement, text)
    return text

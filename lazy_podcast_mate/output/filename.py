"""Render the configured filename pattern into a safe filename."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

_ASCII_SAFE_RE = re.compile(r"[^a-z0-9\u4e00-\u9fff\u3400-\u4dbf]+")
_LEADING_TRAILING_DASHES_RE = re.compile(r"^-+|-+$")


def slugify(title: str, *, max_length: int = 80) -> str:
    """Return a filename-safe slug preserving CJK chars.

    - Normalises Unicode to NFC to avoid combining-mark surprises.
    - Strips file-system-unsafe characters.
    - Collapses runs of unsafe chars to a single `-`.
    - Lower-cases Latin letters; leaves CJK alone.
    - Truncates to `max_length` characters.
    """
    if not title:
        return "untitled"
    normalised = unicodedata.normalize("NFC", title).strip()
    lowered = normalised.lower()
    slug = _ASCII_SAFE_RE.sub("-", lowered)
    slug = _LEADING_TRAILING_DASHES_RE.sub("", slug)
    if not slug:
        return "untitled"
    return slug[:max_length]


def render_filename(
    pattern: str,
    *,
    title: str,
    run_id: str,
    now: datetime | None = None,
) -> str:
    when = now or datetime.now(timezone.utc)
    return pattern.format(
        date=when.strftime("%Y-%m-%d"),
        slug=slugify(title),
        run_id=run_id,
        title=title,
    )

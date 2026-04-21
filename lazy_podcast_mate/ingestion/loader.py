"""Dispatch by extension and apply size limits."""

from __future__ import annotations

from pathlib import Path

from .errors import IngestionError
from .html import read_html
from .markdown import read_markdown
from .models import Article
from .text import read_text

_MARKDOWN_EXTS = {".md", ".markdown"}
_HTML_EXTS = {".html", ".htm"}
_TEXT_EXTS = {".txt"}

SUPPORTED_EXTENSIONS = sorted(_MARKDOWN_EXTS | _HTML_EXTS | _TEXT_EXTS)


def load_article(path: str | Path, *, max_bytes: int) -> Article:
    p = Path(path).expanduser()
    if not p.exists():
        raise IngestionError(f"file not found: {p}")
    if not p.is_file():
        raise IngestionError(f"not a regular file: {p}")

    ext = p.suffix.lower()
    if ext not in (_MARKDOWN_EXTS | _HTML_EXTS | _TEXT_EXTS):
        raise IngestionError(
            f"unsupported extension {ext!r} for {p} "
            f"(supported: {', '.join(SUPPORTED_EXTENSIONS)})"
        )

    size = p.stat().st_size
    if size == 0:
        raise IngestionError(f"empty input: {p}")
    if size > max_bytes:
        raise IngestionError(
            f"file too large: {p} is {size} bytes, max is {max_bytes}"
        )

    data = p.read_bytes()
    if ext in _MARKDOWN_EXTS:
        return read_markdown(p, data)
    if ext in _HTML_EXTS:
        return read_html(p, data)
    return read_text(p, data)

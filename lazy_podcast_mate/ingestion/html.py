"""HTML reader using the stdlib html.parser."""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from .encoding import decode_bytes
from .errors import IngestionError
from .models import Article

_SKIP_TAGS = {
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "noscript",
    "template",
    "svg",
    "iframe",
    "form",
    "button",
}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "section",
    "article", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote",
}


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_title = False
        self._in_h1 = False
        self._title: str | None = None
        self._first_h1: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):  # type: ignore[override]
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag == "h1" and self._first_h1 is None:
            self._in_h1 = True
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str):  # type: ignore[override]
        tag = tag.lower()
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag == "h1":
            self._in_h1 = False
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str):  # type: ignore[override]
        if self._skip_depth:
            return
        if self._in_title:
            self._title = (self._title or "") + data
            return
        if self._in_h1 and self._first_h1 is None:
            # capture text into running h1 buffer
            self._parts.append(data)
            self._h1_accum = (getattr(self, "_h1_accum", "") or "") + data
            return
        self._parts.append(data)

    def handle_endtag_h1_flush(self) -> None:
        pass  # placeholder for symmetry

    @property
    def title(self) -> str:
        t = (self._title or "").strip()
        if t:
            return t
        return (getattr(self, "_h1_accum", "") or "").strip()

    @property
    def body(self) -> str:
        raw = "".join(self._parts)
        # collapse internal whitespace on each line but preserve blank lines
        cleaned_lines = []
        for line in raw.splitlines():
            collapsed = " ".join(line.split())
            cleaned_lines.append(collapsed)
        # collapse runs of blank lines to a single blank line
        out: list[str] = []
        prev_blank = False
        for line in cleaned_lines:
            blank = not line
            if blank and prev_blank:
                continue
            out.append(line)
            prev_blank = blank
        return "\n".join(out).strip()


def read_html(path: Path, data: bytes) -> Article:
    text, encoding = decode_bytes(data, str(path))
    if not text.strip():
        raise IngestionError(f"empty input: {path}")

    extractor = _Extractor()
    extractor.feed(text)
    extractor.close()

    body = extractor.body
    if not body:
        raise IngestionError(f"no spoken content left after stripping markup: {path}")

    return Article(
        title=extractor.title or path.stem,
        body=body,
        source_path=str(path),
        source_format="html",
        detected_encoding=encoding,
    )

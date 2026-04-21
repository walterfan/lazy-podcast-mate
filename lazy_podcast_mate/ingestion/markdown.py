"""Markdown reader: extract title + body, strip non-spoken content.

Non-spoken visual elements — fenced code blocks, images, and Markdown
tables — are replaced with an opaque placeholder token and remembered in
``Article.placeholders``. Inline-link anchors stay in the body (so the
narrator can read the phrase naturally) while the URL is harvested into
``Article.links`` for the show-notes stage.
"""

from __future__ import annotations

import re
from pathlib import Path

from .encoding import decode_bytes
from .errors import IngestionError
from .models import Article, Link, PlaceholderRef
from .placeholders import (
    build_code_placeholder,
    build_image_placeholder,
    build_table_placeholder,
    summarise_markdown_table,
)

# Capture fenced code block with optional language info string.
# Matches both ``` and ~~~ fences.
_FENCED_CODE_RE = re.compile(
    r"(?P<fence>```|~~~)(?P<lang>[^\n`~]*)\n(?P<body>.*?)(?P=fence)",
    re.DOTALL,
)
_INLINE_CODE_RE = re.compile(r"`([^`]*)`")
_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK_RE = re.compile(r"\[(?P<text>[^\]]+)\]\((?P<url>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
# Markdown tables: a sequence of consecutive lines that all start with `|`,
# with at least one separator row made of dashes (|---|---|).
_TABLE_RE = re.compile(
    r"(?:^\|[^\n]*\n)+^\|[\s\-:|]+\|\s*\n(?:^\|[^\n]*\n?)*",
    re.MULTILINE,
)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", re.MULTILINE)
_EMPHASIS_RE = re.compile(r"(\*{1,3}|_{1,3})(.+?)\1")
_STRIKE_RE = re.compile(r"~~(.+?)~~")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
_HR_RE = re.compile(r"^\s*(-\s*){3,}\s*$|^\s*(_\s*){3,}\s*$|^\s*(\*\s*){3,}\s*$", re.MULTILINE)
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.MULTILINE)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_FOOTNOTE_MARKER_RE = re.compile(r"\[\^[^\]]+\]")


def _extract_title(lines: list[str]) -> tuple[str, list[str]]:
    """Return (title, remaining_lines). Title comes from the first H1 if any;
    otherwise the first non-empty line is used (and stays in the body).
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            title = stripped[2:].strip().rstrip("#").strip()
            rest = lines[:i] + lines[i + 1 :]
            return title, rest
    for line in lines:
        if line.strip():
            return line.strip(), lines
    return "", lines


def _harvest_code_blocks(text: str, placeholders: list[PlaceholderRef]) -> str:
    def _repl(match: re.Match) -> str:
        lang = (match.group("lang") or "").strip()
        source = match.group("body")
        index = sum(1 for p in placeholders if p.kind == "code") + 1
        ph = build_code_placeholder(index, language=lang or None, source=source)
        placeholders.append(ph)
        return f"\n{ph.token}\n"

    return _FENCED_CODE_RE.sub(_repl, text)


def _harvest_images(text: str, placeholders: list[PlaceholderRef]) -> str:
    def _repl(match: re.Match) -> str:
        alt = (match.group("alt") or "").strip()
        url = (match.group("url") or "").strip()
        index = sum(1 for p in placeholders if p.kind == "image") + 1
        ph = build_image_placeholder(index, alt=alt, url=url)
        placeholders.append(ph)
        return ph.token

    return _IMAGE_RE.sub(_repl, text)


def _harvest_tables(text: str, placeholders: list[PlaceholderRef]) -> str:
    def _repl(match: re.Match) -> str:
        raw = match.group(0)
        index = sum(1 for p in placeholders if p.kind == "table") + 1
        ph = build_table_placeholder(
            index,
            summary=summarise_markdown_table(raw),
            source=raw.strip(),
        )
        placeholders.append(ph)
        return f"\n{ph.token}\n"

    return _TABLE_RE.sub(_repl, text)


def _harvest_links(text: str, links: list[Link]) -> str:
    """Record every ``[text](url)`` and replace it with just ``text``."""

    def _repl(match: re.Match) -> str:
        anchor = (match.group("text") or "").strip()
        url = (match.group("url") or "").strip()
        if anchor and url and not url.startswith("#"):
            # Dedup by URL, keep the first anchor text we saw.
            if not any(link.url == url for link in links):
                links.append(Link(text=anchor, url=url))
        return anchor

    return _LINK_RE.sub(_repl, text)


def _strip_remaining_markup(text: str) -> str:
    # Inline code stays in the spoken body as bare text (existing behaviour
    # from v0.1.0). Headings/emphasis/strike/blockquotes/lists are structural
    # formatting and get flattened.
    text = _INLINE_CODE_RE.sub(r"\1", text)
    text = _HEADING_RE.sub(r"\1", text)
    text = _EMPHASIS_RE.sub(r"\2", text)
    text = _STRIKE_RE.sub(r"\1", text)
    text = _BLOCKQUOTE_RE.sub("", text)
    text = _HR_RE.sub("", text)
    text = _LIST_MARKER_RE.sub("", text)
    text = _FOOTNOTE_MARKER_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return text


def read_markdown(path: Path, data: bytes) -> Article:
    text, encoding = decode_bytes(data, str(path))
    if not text.strip():
        raise IngestionError(f"empty input: {path}")

    lines = text.splitlines()
    title, remaining = _extract_title(lines)
    body_raw = "\n".join(remaining)

    placeholders: list[PlaceholderRef] = []
    links: list[Link] = []

    # Order matters: code → table → image → link. Fenced code blocks can
    # contain `|` characters that would otherwise match the table regex,
    # and images / links might appear inside stripped sections.
    body_raw = _harvest_code_blocks(body_raw, placeholders)
    body_raw = _harvest_tables(body_raw, placeholders)
    body_raw = _harvest_images(body_raw, placeholders)
    body_raw = _harvest_links(body_raw, links)

    body = _strip_remaining_markup(body_raw).strip()

    if not body:
        raise IngestionError(f"no spoken content left after stripping markup: {path}")

    return Article(
        title=title or path.stem,
        body=body,
        source_path=str(path),
        source_format="markdown",
        detected_encoding=encoding,
        links=links,
        placeholders=placeholders,
    )

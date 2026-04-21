"""Placeholder helpers shared across source-format readers.

The design:

1. Readers detect non-spoken elements (code blocks, images, tables) and
   replace them in the body with an opaque **token** such as
   ``[[LPM:code:1]]``. A ``PlaceholderRef`` records what was replaced.
2. The cleaner later substitutes each token with a human-readable **label**
   (e.g. ``[此处有一段 Python 代码示例]``) so the LLM can decide whether to
   mention the element in a single spoken sentence or skip it entirely.
3. Show-notes read ``article.placeholders`` directly and render the raw
   ``detail`` content back into the markdown notes file.

Tokens must survive Markdown/HTML stripping — they use only ASCII letters,
digits, brackets and colons, which none of our regexes in ``markdown.py``
or ``html.py`` touch.
"""

from __future__ import annotations

import re

from .models import PlaceholderKind, PlaceholderRef

# Token shape: `[[LPM:<kind>:<index>]]`. The double brackets make it
# impossible to confuse with standard Markdown constructs.
TOKEN_RE = re.compile(r"\[\[LPM:(code|image|table):(\d+)\]\]")


def make_token(kind: PlaceholderKind, index: int) -> str:
    return f"[[LPM:{kind}:{index}]]"


def _code_label(language: str | None) -> str:
    language = (language or "").strip()
    if language:
        return f"[此处有一段 {language} 代码示例]"
    return "[此处有一段代码示例]"


def _image_label(alt: str) -> str:
    alt = (alt or "").strip()
    if alt:
        return f"[配图：{alt}]"
    return "[此处有一张配图]"


def _table_label(summary: str) -> str:
    summary = (summary or "").strip()
    if summary:
        return f"[表格：{summary}]"
    return "[此处有一张表格]"


def build_code_placeholder(index: int, *, language: str | None, source: str) -> PlaceholderRef:
    return PlaceholderRef(
        kind="code",
        token=make_token("code", index),
        label=_code_label(language),
        detail=source,
        language=(language or None),
    )


def build_image_placeholder(index: int, *, alt: str, url: str) -> PlaceholderRef:
    # ``detail`` keeps the original URL so show-notes can link / embed it.
    return PlaceholderRef(
        kind="image",
        token=make_token("image", index),
        label=_image_label(alt),
        detail=url.strip(),
    )


def build_table_placeholder(index: int, *, summary: str, source: str) -> PlaceholderRef:
    return PlaceholderRef(
        kind="table",
        token=make_token("table", index),
        label=_table_label(summary),
        detail=source,
    )


def summarise_markdown_table(raw_table: str, *, max_items: int = 4) -> str:
    """Return a short natural-language summary of a Markdown table.

    Strategy: take the header row cells; if there are up to ``max_items`` of
    them, list them as ``X、Y、Z``; otherwise truncate with ``等`` / ``etc.``.
    Falls back to an empty string if the table is malformed.
    """
    for line in raw_table.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        cells = [c for c in cells if c]
        if not cells:
            continue
        if any(set(c) <= {"-", ":"} for c in cells):
            # separator row, skip and keep looking for the header
            continue
        language_is_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in "".join(cells))
        joiner = "、" if language_is_cjk else ", "
        more_marker = " 等" if language_is_cjk else ", etc."
        if len(cells) <= max_items:
            return f"包含 {joiner.join(cells)} {'等项对比' if language_is_cjk else 'columns'}".strip()
        return f"包含 {joiner.join(cells[:max_items])}{more_marker}"
    return ""


def substitute_labels(text: str, placeholders: list[PlaceholderRef]) -> str:
    """Replace every ``[[LPM:...]]`` token in ``text`` with its human label.

    Tokens that don't have a matching ``PlaceholderRef`` (e.g. because the
    article survived serialisation/deserialisation with a corrupted list)
    are replaced with an empty string so they never leak into the LLM prompt.
    """
    by_token = {p.token: p for p in placeholders}

    def _repl(match: re.Match) -> str:
        ph = by_token.get(match.group(0))
        return ph.label if ph is not None else ""

    return TOKEN_RE.sub(_repl, text)

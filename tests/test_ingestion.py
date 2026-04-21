"""Tests for ingestion readers."""

from __future__ import annotations

import pytest

from lazy_podcast_mate.ingestion.errors import IngestionError
from lazy_podcast_mate.ingestion.loader import load_article


def test_markdown_reader_extracts_title_and_replaces_visual_content(tmp_path):
    f = tmp_path / "post.md"
    f.write_text(
        "# Hello World\n\n"
        "This is an **intro** paragraph with a [link](https://example.com).\n\n"
        "```python\nprint('secret')\n```\n\n"
        "And `inline_code` should stay as text.\n\n"
        "![AWS diagram](img.png)\n\n"
        "- item one\n- item two\n",
        encoding="utf-8",
    )
    article = load_article(f, max_bytes=1_000_000)
    assert article.title == "Hello World"
    assert article.source_format == "markdown"
    # Narrative text survives.
    assert "intro" in article.body
    assert "link" in article.body  # anchor text is preserved, URL is not
    assert "https://example.com" not in article.body
    assert "item one" in article.body
    # Inline code loses its backticks but the identifier stays readable.
    assert "inline_code" in article.body
    # Fenced code block becomes a placeholder token, not raw code.
    assert "print('secret')" not in article.body
    assert "[[LPM:code:1]]" in article.body
    # Image becomes a placeholder token, not bare alt text.
    assert "[[LPM:image:1]]" in article.body
    # Link URL is harvested for show notes.
    assert len(article.links) == 1
    assert article.links[0].text == "link"
    assert article.links[0].url == "https://example.com"
    # Placeholders are available for show notes.
    kinds = {p.kind for p in article.placeholders}
    assert kinds == {"code", "image"}
    code_ph = next(p for p in article.placeholders if p.kind == "code")
    assert code_ph.language == "python"
    assert "print('secret')" in code_ph.detail
    image_ph = next(p for p in article.placeholders if p.kind == "image")
    assert image_ph.detail == "img.png"
    assert "AWS diagram" in image_ph.label


def test_markdown_reader_summarises_table(tmp_path):
    f = tmp_path / "table.md"
    f.write_text(
        "# Comparison\n\n"
        "Intro paragraph.\n\n"
        "| Provider | Free tier | Quality |\n"
        "|----------|-----------|---------|\n"
        "| Azure    | 500k chars| High    |\n"
        "| Volcano  | Trial     | High    |\n\n"
        "Closing paragraph.\n",
        encoding="utf-8",
    )
    article = load_article(f, max_bytes=1_000_000)
    # Raw table bars do not leak into the body.
    assert "|" not in article.body
    # Body keeps a single placeholder token where the table used to be.
    assert "[[LPM:table:1]]" in article.body
    # Placeholder records a short natural-language summary for the cleaner
    # to substitute in front of the LLM.
    tables = [p for p in article.placeholders if p.kind == "table"]
    assert len(tables) == 1
    assert "Provider" in tables[0].label or "Provider" in tables[0].detail
    assert "Free tier" in tables[0].label


def test_markdown_reader_dedups_links_by_url(tmp_path):
    f = tmp_path / "links.md"
    f.write_text(
        "# Title\n\n"
        "See [our docs](https://example.com/docs) and again [the docs](https://example.com/docs).\n"
        "Also [another page](https://example.com/other).\n",
        encoding="utf-8",
    )
    article = load_article(f, max_bytes=1_000_000)
    urls = [link.url for link in article.links]
    assert urls == ["https://example.com/docs", "https://example.com/other"]
    # Both anchors survive in the body; URLs don't.
    assert "our docs" in article.body
    assert "the docs" in article.body
    assert "https://example.com" not in article.body


def test_html_reader_extracts_visible_text(tmp_path):
    f = tmp_path / "page.html"
    f.write_text(
        "<html><head><title>Doc Title</title>"
        "<style>body { color: red }</style></head>"
        "<body><nav>skip me</nav>"
        "<h1>Header Ignored For Title</h1>"
        "<p>First paragraph.</p>"
        "<script>evil()</script>"
        "<p>Second paragraph.</p>"
        "</body></html>",
        encoding="utf-8",
    )
    article = load_article(f, max_bytes=1_000_000)
    assert article.title == "Doc Title"
    assert "First paragraph." in article.body
    assert "Second paragraph." in article.body
    assert "skip me" not in article.body
    assert "evil()" not in article.body
    assert "color: red" not in article.body


def test_text_reader_uses_first_short_line_as_title(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("My Title\n\nThis is the body.\nWith two lines.\n", encoding="utf-8")
    article = load_article(f, max_bytes=1_000_000)
    assert article.title == "My Title"
    assert "This is the body." in article.body


def test_empty_file_rejected(tmp_path):
    f = tmp_path / "empty.md"
    f.write_text("", encoding="utf-8")
    with pytest.raises(IngestionError, match="empty"):
        load_article(f, max_bytes=1_000_000)


def test_unsupported_extension_rejected(tmp_path):
    f = tmp_path / "article.pdf"
    f.write_bytes(b"%PDF-1.4 not really")
    with pytest.raises(IngestionError, match="unsupported extension"):
        load_article(f, max_bytes=1_000_000)


def test_max_size_enforced(tmp_path):
    f = tmp_path / "big.md"
    f.write_text("# t\n" + ("x" * 1000), encoding="utf-8")
    with pytest.raises(IngestionError, match="too large"):
        load_article(f, max_bytes=100)


def test_undecodable_bytes_rejected(tmp_path):
    f = tmp_path / "bad.txt"
    # Bytes that are not UTF-8 and mostly control chars -> latin-1 fallback fails the
    # printability check, so IngestionError is raised.
    f.write_bytes(bytes([0xFF, 0xFE, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]))
    with pytest.raises(IngestionError):
        load_article(f, max_bytes=1_000_000)


def test_gbk_encoding_is_detected(tmp_path):
    f = tmp_path / "zh.txt"
    f.write_bytes("标题\n\n正文内容".encode("gbk"))
    article = load_article(f, max_bytes=1_000_000)
    assert article.title == "标题"
    assert article.detected_encoding in ("gbk", "gb18030")


def test_markdown_without_h1_uses_first_line(tmp_path):
    f = tmp_path / "post.md"
    f.write_text("First line\n\nBody paragraph.\n", encoding="utf-8")
    article = load_article(f, max_bytes=1_000_000)
    assert article.title == "First line"
    assert "Body paragraph." in article.body

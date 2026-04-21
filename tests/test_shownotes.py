"""Tests for show-notes rendering and writing."""

from __future__ import annotations

from pathlib import Path

import pytest

from lazy_podcast_mate.config.schema import ID3Config, OutputConfig
from lazy_podcast_mate.ingestion.models import Article, Link, PlaceholderRef
from lazy_podcast_mate.output.errors import OutputExistsError
from lazy_podcast_mate.output.shownotes import (
    ShowNotesContext,
    render_show_notes,
    write_show_notes,
)


def _make_article(**overrides) -> Article:
    defaults = dict(
        title="Hello World",
        body="body text",
        source_path="/tmp/post.md",
        source_format="markdown",
        detected_encoding="utf-8",
        links=[],
        placeholders=[],
    )
    defaults.update(overrides)
    return Article(**defaults)


def _make_output_config(directory: Path, *, on_existing: str = "error") -> OutputConfig:
    return OutputConfig(
        directory=str(directory),
        filename_pattern="{date}-{slug}.mp3",
        on_existing=on_existing,
        history_file=str(directory / "history.jsonl"),
        id3=ID3Config(),
    )


def _ctx(article: Article, *, audio_filename: str = "2026-04-19-hello.mp3") -> ShowNotesContext:
    return ShowNotesContext(
        title=article.title,
        source_path=article.source_path,
        run_id="run-123",
        article=article,
        audio_filename=audio_filename,
    )


def test_render_handles_empty_article():
    article = _make_article()
    md = render_show_notes(_ctx(article))
    assert "# Hello World" in md
    assert "Run ID: `run-123`" in md
    assert "Source: `/tmp/post.md`" in md
    assert "No external links" in md
    # No empty section headers should appear when the article is bare.
    assert "## 原文链接" not in md
    assert "## 代码片段" not in md
    assert "## 表格" not in md


def test_render_lists_links_in_order_and_dedups_via_ingestion():
    """Show notes should print links exactly in the order ingestion recorded
    them (ingestion handles dedup). Anchor text is preserved for readability.
    """
    article = _make_article(
        links=[
            Link(text="our docs", url="https://example.com/docs"),
            Link(text="related post", url="https://example.com/post"),
        ]
    )
    md = render_show_notes(_ctx(article))
    assert "## 原文链接" in md
    idx_docs = md.index("https://example.com/docs")
    idx_post = md.index("https://example.com/post")
    assert idx_docs < idx_post
    assert "[our docs](https://example.com/docs)" in md
    assert "[related post](https://example.com/post)" in md


def test_render_includes_code_image_and_table_sections():
    article = _make_article(
        placeholders=[
            PlaceholderRef(
                kind="code",
                token="[[LPM:code:1]]",
                label="[此处有一段 Python 代码示例]",
                detail="print('hello')\nprint('world')\n",
                language="python",
            ),
            PlaceholderRef(
                kind="image",
                token="[[LPM:image:1]]",
                label="[配图：AWS architecture]",
                detail="https://cdn.example.com/aws.png",
            ),
            PlaceholderRef(
                kind="table",
                token="[[LPM:table:1]]",
                label="[表格：包含 Provider、Free tier、Quality 等项对比]",
                detail="| Provider | Free tier | Quality |\n|---|---|---|\n| Azure | 500k | High |",
            ),
        ]
    )
    md = render_show_notes(_ctx(article))

    assert "## 代码片段" in md
    # Fenced code block should use the detected language.
    assert "```python\nprint('hello')" in md
    assert "```\n" in md  # fence closes

    assert "## 配图" in md
    # Rendered as a markdown image with alt + URL.
    assert "![AWS architecture](https://cdn.example.com/aws.png)" in md

    assert "## 表格" in md
    # Raw table markdown is preserved verbatim so readers see the original.
    assert "| Provider | Free tier | Quality |" in md


def test_render_includes_audio_filename_when_given():
    article = _make_article()
    md = render_show_notes(_ctx(article, audio_filename="episode-42.mp3"))
    assert "Audio: `episode-42.mp3`" in md


def test_write_creates_file_next_to_audio(tmp_path):
    audio = tmp_path / "2026-04-19-hello.mp3"
    audio.write_bytes(b"fake mp3")
    article = _make_article(
        links=[Link(text="docs", url="https://example.com")],
    )
    config = _make_output_config(tmp_path)

    notes_path = write_show_notes(_ctx(article), audio_path=audio, config=config)

    assert notes_path == tmp_path / "2026-04-19-hello.shownotes.md"
    assert notes_path.exists()
    content = notes_path.read_text(encoding="utf-8")
    assert "# Hello World" in content
    assert "https://example.com" in content


def test_write_refuses_to_overwrite_when_on_existing_error(tmp_path):
    audio = tmp_path / "2026-04-19-hello.mp3"
    audio.write_bytes(b"fake mp3")
    notes = tmp_path / "2026-04-19-hello.shownotes.md"
    notes.write_text("PRE-EXISTING", encoding="utf-8")

    config = _make_output_config(tmp_path, on_existing="error")
    with pytest.raises(OutputExistsError):
        write_show_notes(_ctx(_make_article()), audio_path=audio, config=config)
    # Original untouched.
    assert notes.read_text(encoding="utf-8") == "PRE-EXISTING"


def test_write_auto_suffixes_when_on_existing_suffix(tmp_path):
    audio = tmp_path / "2026-04-19-hello.mp3"
    audio.write_bytes(b"fake mp3")
    (tmp_path / "2026-04-19-hello.shownotes.md").write_text("first", encoding="utf-8")

    config = _make_output_config(tmp_path, on_existing="suffix")
    out = write_show_notes(_ctx(_make_article()), audio_path=audio, config=config)

    assert out.name == "2026-04-19-hello.shownotes-1.md"
    # Original untouched.
    assert (tmp_path / "2026-04-19-hello.shownotes.md").read_text(encoding="utf-8") == "first"


def test_render_never_leaks_placeholder_tokens():
    """Tokens like ``[[LPM:code:1]]`` must not appear in show notes —
    readers should see the human-friendly label and the raw content only.
    """
    article = _make_article(
        placeholders=[
            PlaceholderRef(
                kind="code",
                token="[[LPM:code:1]]",
                label="[此处有一段代码示例]",
                detail="pass",
                language=None,
            ),
        ]
    )
    md = render_show_notes(_ctx(article))
    assert "[[LPM:" not in md

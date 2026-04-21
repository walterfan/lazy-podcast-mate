"""Render show-notes markdown alongside the final MP3.

A show-notes file is a companion to the spoken podcast that surfaces the
non-spoken material dropped during script rewriting:

- Every hyperlink harvested from the source article, so listeners have a
  canonical reference list of URLs.
- Every code block, image, and table placeholder that was mentioned (or
  dropped) in the script, so the listener can still *see* the visual
  content when they come back to the post.

The file is plain markdown so it can be pasted into blog CMS / feed
reader / RSS description boxes verbatim.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.schema import OutputConfig
from ..ingestion.models import Article
from .errors import OutputExistsError


@dataclass(frozen=True)
class ShowNotesContext:
    """Inputs for :func:`render_show_notes`.

    Keeping this a tiny dataclass lets the orchestrator assemble arguments
    explicitly and the unit tests stay readable.
    """

    title: str
    source_path: str
    run_id: str
    article: Article
    audio_filename: str | None = None


def _render_link_section(article: Article) -> list[str]:
    if not article.links:
        return []
    lines = ["## 原文链接 / Links", ""]
    for link in article.links:
        text = link.text.strip() or link.url
        lines.append(f"- [{text}]({link.url})")
    lines.append("")
    return lines


def _render_placeholder_section(article: Article) -> list[str]:
    if not article.placeholders:
        return []
    codes = [p for p in article.placeholders if p.kind == "code"]
    images = [p for p in article.placeholders if p.kind == "image"]
    tables = [p for p in article.placeholders if p.kind == "table"]

    lines: list[str] = []

    if codes:
        lines += ["## 代码片段 / Code snippets", ""]
        for i, ph in enumerate(codes, 1):
            heading = f"### {i}. {ph.label}"
            if ph.language:
                heading += f"（{ph.language}）"
            lines.append(heading)
            lines.append("")
            fence_lang = ph.language or ""
            lines.append(f"```{fence_lang}")
            # ``detail`` already preserves the original source; strip trailing
            # newlines so the fence doesn't pick up an extra blank line.
            lines.append(ph.detail.rstrip("\n"))
            lines.append("```")
            lines.append("")

    if images:
        lines += ["## 配图 / Figures", ""]
        for i, ph in enumerate(images, 1):
            alt = ph.label.replace("[配图：", "").replace("[此处有一张配图]", "").rstrip("]").strip()
            alt_text = alt or "figure"
            if ph.detail:
                lines.append(f"{i}. ![{alt_text}]({ph.detail})")
            else:
                lines.append(f"{i}. {ph.label}")
        lines.append("")

    if tables:
        lines += ["## 表格 / Tables", ""]
        for i, ph in enumerate(tables, 1):
            lines.append(f"### {i}. {ph.label}")
            lines.append("")
            lines.append(ph.detail)
            lines.append("")

    return lines


def render_show_notes(ctx: ShowNotesContext) -> str:
    """Return the complete show-notes markdown body as a single string."""
    lines: list[str] = [f"# {ctx.title}", ""]

    meta_lines = [
        f"- Source: `{ctx.source_path}`",
        f"- Run ID: `{ctx.run_id}`",
    ]
    if ctx.audio_filename:
        meta_lines.append(f"- Audio: `{ctx.audio_filename}`")
    lines += meta_lines + [""]

    link_lines = _render_link_section(ctx.article)
    placeholder_lines = _render_placeholder_section(ctx.article)

    if not link_lines and not placeholder_lines:
        lines.append("_No external links, code snippets, figures, or tables were detected in the source article._")
        lines.append("")
    else:
        lines += link_lines
        lines += placeholder_lines

    # Guarantee a trailing newline.
    body = "\n".join(lines)
    if not body.endswith("\n"):
        body += "\n"
    return body


def _candidate_with_suffix(target: Path) -> Path:
    stem, suffix = target.stem, target.suffix
    counter = 1
    while True:
        candidate = target.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def write_show_notes(
    ctx: ShowNotesContext,
    *,
    audio_path: Path,
    config: OutputConfig,
) -> Path:
    """Write the show-notes markdown next to ``audio_path``.

    The filename mirrors the final MP3 — ``<stem>.shownotes.md`` — so the two
    files are trivially discoverable together. ``config.on_existing`` is
    honoured exactly like :func:`~lazy_podcast_mate.output.writer.place_output`:
    ``error`` refuses to overwrite, ``suffix`` appends ``-1``/``-2``/….
    """
    out_dir = Path(config.directory).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{audio_path.stem}.shownotes.md"

    if target.exists():
        if config.on_existing == "error":
            raise OutputExistsError(
                f"refusing to overwrite existing show-notes file: {target}. "
                "Set output.on_existing=suffix to auto-rename, or remove the file."
            )
        target = _candidate_with_suffix(target)

    content = render_show_notes(ctx)
    target.write_text(content, encoding="utf-8")
    return target


__all__ = [
    "ShowNotesContext",
    "render_show_notes",
    "write_show_notes",
]

"""Plain text reader."""

from __future__ import annotations

from pathlib import Path

from .encoding import decode_bytes
from .errors import IngestionError
from .models import Article

_SHORT_LINE_CHARS = 120  # lines shorter than this are candidates for a title


def read_text(path: Path, data: bytes) -> Article:
    text, encoding = decode_bytes(data, str(path))
    if not text.strip():
        raise IngestionError(f"empty input: {path}")

    lines = text.splitlines()
    title = ""
    body_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            title = stripped
            body_start = i + 1
            break

    # If the first non-empty line is long, treat the filename as the title
    # and include the whole text as the body.
    if len(title) > _SHORT_LINE_CHARS:
        title = path.stem
        body_start = 0

    body = "\n".join(lines[body_start:]).strip()
    if not body:
        # Allow title-only files: fall back to title as body so TTS has content.
        body = title

    return Article(
        title=title or path.stem,
        body=body,
        source_path=str(path),
        source_format="text",
        detected_encoding=encoding,
    )

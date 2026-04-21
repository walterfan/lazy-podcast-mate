"""Concatenate chunk audio files in order, with an inter-chunk silence."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment

from .errors import PostProductionError


def concat_chunks(chunk_paths: list[Path], *, silence_ms: int) -> AudioSegment:
    """Concatenate `chunk_paths` in the given order.

    The caller is responsible for ordering. Missing or empty files raise
    `PostProductionError` with the offending path.
    """
    if not chunk_paths:
        raise PostProductionError("no chunk audio files to concatenate")

    silence = AudioSegment.silent(duration=max(0, silence_ms))
    combined: AudioSegment | None = None

    for i, path in enumerate(chunk_paths):
        if not path.exists() or path.stat().st_size == 0:
            raise PostProductionError(f"chunk audio missing or empty: {path}")
        try:
            segment = AudioSegment.from_file(path)
        except Exception as exc:
            raise PostProductionError(f"could not decode {path}: {exc}") from exc
        if combined is None:
            combined = segment
        else:
            combined = combined + silence + segment

    assert combined is not None
    return combined

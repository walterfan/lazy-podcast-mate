"""Apply fade-in and fade-out to an AudioSegment."""

from __future__ import annotations

from pydub import AudioSegment


def apply_fades(
    audio: AudioSegment,
    *,
    fade_in_ms: int,
    fade_out_ms: int,
) -> AudioSegment:
    result = audio
    if fade_in_ms > 0:
        result = result.fade_in(min(fade_in_ms, len(result)))
    if fade_out_ms > 0:
        result = result.fade_out(min(fade_out_ms, len(result)))
    return result

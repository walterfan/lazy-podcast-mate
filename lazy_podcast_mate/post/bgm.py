"""Mix background music underneath the voice track."""

from __future__ import annotations

import math
from pathlib import Path

from pydub import AudioSegment

from .errors import PostProductionError


def _rms_to_db(rms: float) -> float:
    if rms <= 0:
        return -float("inf")
    return 20.0 * math.log10(rms)


def mix_bgm(
    voice: AudioSegment,
    bgm_path: Path,
    *,
    ratio: float,
) -> AudioSegment:
    """Overlay `bgm_path` under `voice` at a target RMS `ratio` of the voice.

    `ratio` must be in [0.10, 0.15]. Raises `PostProductionError` otherwise.
    """
    if not (0.10 <= ratio <= 0.15):
        raise PostProductionError(
            f"bgm ratio must be within [0.10, 0.15], got {ratio}"
        )
    if not bgm_path.exists():
        raise PostProductionError(f"bgm file not found: {bgm_path}")

    try:
        bgm = AudioSegment.from_file(bgm_path)
    except Exception as exc:
        raise PostProductionError(f"could not decode bgm {bgm_path}: {exc}") from exc

    # Loop or trim BGM to match voice length.
    if len(bgm) < len(voice):
        repeats = (len(voice) // max(1, len(bgm))) + 1
        bgm = bgm * repeats
    bgm = bgm[: len(voice)]

    voice_rms = voice.rms
    if voice_rms <= 0:
        raise PostProductionError("voice track is silent; cannot compute BGM level")

    target_bgm_rms = voice_rms * ratio
    current_bgm_rms = max(bgm.rms, 1)
    gain_db = _rms_to_db(target_bgm_rms) - _rms_to_db(current_bgm_rms)
    bgm = bgm.apply_gain(gain_db)

    return voice.overlay(bgm)

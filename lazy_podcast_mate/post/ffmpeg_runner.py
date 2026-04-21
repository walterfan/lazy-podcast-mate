"""Shared helper to invoke ffmpeg via subprocess."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from .errors import PostProductionError

log = logging.getLogger(__name__)


def run_ffmpeg(
    args: list[str],
    *,
    timeout: int = 600,
    loglevel: str = "error",
) -> subprocess.CompletedProcess:
    """Run `ffmpeg <args>` and return the completed process.

    `loglevel` controls ffmpeg's own `-loglevel` flag. Use the default
    ``"error"`` for plain transcode/mix steps, and ``"info"`` (or higher)
    when you need to parse filter output such as `loudnorm`'s JSON stats —
    ffmpeg writes those at info level and they are otherwise silently
    discarded.

    Raises `PostProductionError` on non-zero exit, forwarding stderr.
    """
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", loglevel, "-nostdin", "-y", *args]
    log.debug("running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(  # noqa: S603 — controlled args
            cmd,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise PostProductionError(f"ffmpeg failed to start: {exc}") from exc

    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="replace")
        raise PostProductionError(
            f"ffmpeg exited {proc.returncode}: {stderr.strip()[:800]}"
        )
    return proc


def read_ffmpeg_output(
    args: list[str],
    *,
    timeout: int = 600,
    loglevel: str = "info",
) -> str:
    """Like `run_ffmpeg`, but returns stderr as a string.

    Defaults to ``loglevel="info"`` because every caller of this helper
    needs to parse filter-level stats (e.g. loudnorm JSON) that ffmpeg only
    prints at info level or higher.
    """
    proc = run_ffmpeg(args, timeout=timeout, loglevel=loglevel)
    return (proc.stderr or b"").decode("utf-8", errors="replace")


def tmp_wav_export(audio, path: Path) -> Path:
    """Export an AudioSegment to a 48 kHz stereo WAV for ffmpeg consumption."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audio.set_frame_rate(48000).set_channels(2).export(
        path, format="wav", parameters=["-acodec", "pcm_s16le"]
    )
    return path

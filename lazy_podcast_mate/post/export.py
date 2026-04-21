"""Export to 320 kbps CBR MP3 and verify the encoded bitrate."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from pydub import AudioSegment

from .errors import PostProductionError

log = logging.getLogger(__name__)


_TARGET_BITRATE_KBPS = 320
_BITRATE_TOLERANCE_KBPS = 16  # allow small rounding around exact 320


def export_mp3(
    audio: AudioSegment,
    path: Path,
    *,
    sample_rate: int = 48000,
) -> None:
    """Export `audio` as a 320 kbps CBR MP3, 44.1 or 48 kHz stereo."""
    if sample_rate not in (44100, 48000):
        raise PostProductionError(f"unsupported sample_rate {sample_rate}; must be 44100 or 48000")

    path.parent.mkdir(parents=True, exist_ok=True)
    prepared = audio.set_frame_rate(sample_rate).set_channels(2)
    prepared.export(
        path,
        format="mp3",
        bitrate=f"{_TARGET_BITRATE_KBPS}k",
        parameters=["-ac", "2", "-ar", str(sample_rate), "-b:a", f"{_TARGET_BITRATE_KBPS}k"],
    )

    # Verify encoded bitrate.
    actual = _probe_bitrate_kbps(path)
    if actual < _TARGET_BITRATE_KBPS - _BITRATE_TOLERANCE_KBPS:
        raise PostProductionError(
            f"encoded bitrate {actual} kbps is below target {_TARGET_BITRATE_KBPS} kbps"
        )
    log.info("exported %s at ~%d kbps", path, actual)


def _probe_bitrate_kbps(path: Path) -> int:
    try:
        proc = subprocess.run(  # noqa: S603
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=bit_rate",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise PostProductionError(f"ffprobe failed to inspect {path}: {exc}") from exc
    value = (proc.stdout or b"").decode("utf-8", errors="replace").strip()
    try:
        return int(value) // 1000
    except ValueError:
        # Some muxers omit per-stream bitrate for CBR; fall back to format-level.
        try:
            proc2 = subprocess.run(  # noqa: S603
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=bit_rate",
                    "-of",
                    "default=nokey=1:noprint_wrappers=1",
                    str(path),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise PostProductionError(
                f"ffprobe failed to inspect format bitrate for {path}: {exc}"
            ) from exc
        value2 = (proc2.stdout or b"").decode("utf-8", errors="replace").strip()
        try:
            return int(value2) // 1000
        except ValueError as exc:
            raise PostProductionError(
                f"ffprobe did not report a numeric bitrate for {path}: {value2!r}"
            ) from exc

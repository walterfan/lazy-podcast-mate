"""Verify ffmpeg is installed at start-up."""

from __future__ import annotations

import shutil
import subprocess

from .errors import FFmpegMissingError

_INSTALL_HINT = (
    "ffmpeg is required but was not found on PATH.\n"
    "  macOS:   brew install ffmpeg\n"
    "  Ubuntu:  sudo apt install ffmpeg\n"
    "  Windows: https://ffmpeg.org/download.html"
)


def ensure_ffmpeg_available(which=shutil.which, run=subprocess.run) -> str:
    """Return the absolute path to `ffmpeg`, or raise `FFmpegMissingError`."""
    path = which("ffmpeg")
    if not path:
        raise FFmpegMissingError(_INSTALL_HINT)
    try:
        run(
            [path, "-version"],
            check=True,
            capture_output=True,
            timeout=10,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        raise FFmpegMissingError(f"{path} is not executable: {exc}\n\n{_INSTALL_HINT}") from exc
    return path

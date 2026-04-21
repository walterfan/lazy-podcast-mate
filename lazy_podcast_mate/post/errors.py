"""Post-production errors."""

from __future__ import annotations


class PostProductionError(Exception):
    """Raised when an audio post-production step fails."""


class FFmpegMissingError(PostProductionError):
    """ffmpeg binary is not on PATH."""

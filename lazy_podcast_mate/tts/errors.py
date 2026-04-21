"""TTS errors."""

from __future__ import annotations


class TTSError(Exception):
    """Base TTS error."""


class TransientTTSError(TTSError):
    """Retryable TTS failure (network / 429 / 5xx)."""


class PermanentTTSError(TTSError):
    """Non-retryable TTS failure (auth, 4xx, bad response)."""

"""`TTSSynthesizer` Protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ..chunking.models import TextChunk

AudioFormat = Literal["mp3", "wav"]


@dataclass(frozen=True)
class VoiceConfig:
    voice_id: str
    rate: float
    volume: float


class TTSSynthesizer(Protocol):
    """Synthesise a single text chunk into audio bytes."""

    provider_name: str
    supports_concurrency: int
    audio_format: AudioFormat

    def synthesize(self, chunk: TextChunk, *, voice: VoiceConfig) -> bytes:
        ...

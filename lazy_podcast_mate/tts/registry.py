"""Map `TTS_PROVIDER` to a concrete `TTSSynthesizer` factory."""

from __future__ import annotations

from ..config.env import EnvConfig
from ..config.schema import TTSConfig
from .azure import AzureTTS
from .base import TTSSynthesizer
from .cosyvoice import CosyVoiceTTS
from .errors import PermanentTTSError
from .volcano import VolcanoTTS


def build_synthesizer(env: EnvConfig, config: TTSConfig) -> TTSSynthesizer:
    provider = (env.tts_provider or "").lower()
    if provider == "azure":
        return AzureTTS.from_env(env, config)
    if provider == "volcano":
        return VolcanoTTS.from_env(env, config)
    if provider == "cosyvoice":
        return CosyVoiceTTS.from_env(env, config)
    raise PermanentTTSError(f"unsupported TTS_PROVIDER: {provider!r}")

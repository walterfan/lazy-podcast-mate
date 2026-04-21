"""CosyVoice adapter (self-hosted or DashScope-compatible endpoint).

Assumes a simple JSON POST that returns audio bytes or a base64 payload.
Many deployments use the DashScope schema; we default to:
    POST {base_url}/services/aigc/multimodal-generation/generation
with a fallback of returning the raw body as audio when `Content-Type`
is an audio type.
"""

from __future__ import annotations

import base64

import requests

from ..chunking.models import TextChunk
from ..config.env import EnvConfig
from ..config.schema import TTSConfig
from .base import TTSSynthesizer, VoiceConfig
from .errors import PermanentTTSError, TransientTTSError

_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class CosyVoiceTTS(TTSSynthesizer):
    provider_name = "cosyvoice"
    supports_concurrency = 4
    audio_format = "mp3"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        config: TTSConfig,
        timeout_seconds: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._config = config
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_env(cls, env: EnvConfig, config: TTSConfig) -> "CosyVoiceTTS":
        assert env.tts_api_key and env.tts_base_url
        return cls(api_key=env.tts_api_key, base_url=env.tts_base_url, config=config)

    def synthesize(self, chunk: TextChunk, *, voice: VoiceConfig) -> bytes:
        url = f"{self._base_url}/tts"
        try:
            response = self._session.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "text": chunk.text,
                    "voice": voice.voice_id,
                    "speed": voice.rate,
                    "volume": voice.volume,
                    "format": "mp3",
                },
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise TransientTTSError(f"network error: {exc}") from exc

        if response.status_code in _TRANSIENT_STATUS:
            raise TransientTTSError(
                f"cosyvoice returned HTTP {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise PermanentTTSError(
                f"cosyvoice returned HTTP {response.status_code}: {response.text[:500]}"
            )

        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("audio/"):
            if not response.content:
                raise PermanentTTSError("cosyvoice returned empty audio body")
            return response.content

        try:
            body = response.json()
        except ValueError as exc:
            raise PermanentTTSError(
                f"cosyvoice returned non-audio, non-JSON body: {content_type!r}"
            ) from exc

        data_b64 = body.get("audio") or body.get("data")
        if not data_b64:
            raise PermanentTTSError("cosyvoice JSON response missing `audio`/`data` field")
        try:
            return base64.b64decode(data_b64)
        except (ValueError, TypeError) as exc:
            raise PermanentTTSError(f"cosyvoice returned invalid base64: {exc}") from exc

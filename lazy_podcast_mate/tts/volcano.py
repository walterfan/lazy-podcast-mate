"""Volcano Engine (火山引擎) TTS adapter.

Uses the long-text / streaming synthesis REST API:
    POST https://openspeech.bytedance.com/api/v1/tts
    Auth: Bearer;{token}
Returns base64-encoded audio in JSON body.
"""

from __future__ import annotations

import base64
import uuid

import requests

from ..chunking.models import TextChunk
from ..config.env import EnvConfig
from ..config.schema import TTSConfig
from .base import TTSSynthesizer, VoiceConfig
from .errors import PermanentTTSError, TransientTTSError

_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
_DEFAULT_URL = "https://openspeech.bytedance.com/api/v1/tts"


class VolcanoTTS(TTSSynthesizer):
    provider_name = "volcano"
    supports_concurrency = 4
    audio_format = "mp3"

    def __init__(
        self,
        *,
        api_key: str,
        app_id: str,
        cluster: str,
        config: TTSConfig,
        url: str = _DEFAULT_URL,
        timeout_seconds: float = 60.0,
        session: requests.Session | None = None,
    ) -> None:
        self._api_key = api_key
        self._app_id = app_id
        self._cluster = cluster
        self._config = config
        self._url = url
        self._timeout = timeout_seconds
        self._session = session or requests.Session()

    @classmethod
    def from_env(cls, env: EnvConfig, config: TTSConfig) -> "VolcanoTTS":
        assert env.tts_api_key and env.tts_app_id and env.tts_cluster
        return cls(
            api_key=env.tts_api_key,
            app_id=env.tts_app_id,
            cluster=env.tts_cluster,
            config=config,
            url=env.tts_base_url or _DEFAULT_URL,
        )

    def synthesize(self, chunk: TextChunk, *, voice: VoiceConfig) -> bytes:
        payload = {
            "app": {
                "appid": self._app_id,
                "token": self._api_key,
                "cluster": self._cluster,
            },
            "user": {"uid": "lazy-podcast-mate"},
            "audio": {
                "voice_type": voice.voice_id,
                "encoding": "mp3",
                "speed_ratio": voice.rate,
                "volume_ratio": voice.volume,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": chunk.text,
                "operation": "query",
            },
        }
        try:
            response = self._session.post(
                self._url,
                headers={
                    "Authorization": f"Bearer;{self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise TransientTTSError(f"network error: {exc}") from exc

        if response.status_code in _TRANSIENT_STATUS:
            raise TransientTTSError(
                f"volcano tts returned HTTP {response.status_code}: {response.text[:200]}"
            )
        if response.status_code >= 400:
            raise PermanentTTSError(
                f"volcano tts returned HTTP {response.status_code}: {response.text[:500]}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise PermanentTTSError(f"volcano tts returned non-JSON: {exc}") from exc

        code = body.get("code")
        if code not in (0, 3000):  # 3000 is the documented success code
            message = body.get("message") or body.get("Message") or "unknown error"
            if code in (3001, 3002, 3003, 3004, 3005):
                raise TransientTTSError(f"volcano tts transient error {code}: {message}")
            raise PermanentTTSError(f"volcano tts error {code}: {message}")

        data_b64 = body.get("data")
        if not data_b64:
            raise PermanentTTSError("volcano tts response missing `data`")
        try:
            return base64.b64decode(data_b64)
        except (ValueError, TypeError) as exc:
            raise PermanentTTSError(f"volcano tts returned invalid base64: {exc}") from exc

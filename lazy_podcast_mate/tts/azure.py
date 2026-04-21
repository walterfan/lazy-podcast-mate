"""Azure Cognitive Services Text-to-Speech adapter.

Uses the REST API:
    POST https://{region}.tts.speech.microsoft.com/cognitiveservices/v1
    Headers: Ocp-Apim-Subscription-Key, X-Microsoft-OutputFormat, Content-Type: application/ssml+xml
Returns MP3 bytes directly.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

import requests

from ..chunking.models import TextChunk
from ..config.env import EnvConfig
from ..config.schema import TTSConfig
from .base import TTSSynthesizer, VoiceConfig
from .errors import PermanentTTSError, TransientTTSError

_TRANSIENT_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

# Azure surfaces the real reason for 400s in response headers, not the body.
# Example: X-Microsoft-Reason: InvalidVoice, X-RequestId: ...
_AZURE_DIAGNOSTIC_HEADERS = (
    "X-Microsoft-Reason",
    "X-RequestId",
    "apim-request-id",
    "WWW-Authenticate",
)


def _infer_xml_lang(voice_id: str) -> str:
    """Infer BCP-47 xml:lang from a standard Azure neural-voice id.

    ``zh-CN-YunjianNeural`` -> ``zh-CN``
    ``en-US-JennyNeural``   -> ``en-US``
    Falls back to ``zh-CN`` for legacy/custom voice ids so existing
    configurations keep working.
    """
    parts = voice_id.split("-")
    if len(parts) >= 2 and len(parts[0]) == 2 and parts[1].isalpha():
        return f"{parts[0]}-{parts[1]}"
    return "zh-CN"


def _build_ssml(text: str, voice: VoiceConfig, *, xml_lang: str) -> str:
    rate_percent = f"{int((voice.rate - 1.0) * 100):+d}%"
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="{xml_lang}">'
        f'<voice name="{escape(voice.voice_id)}">'
        f'<prosody rate="{rate_percent}">{escape(text)}</prosody>'
        "</voice></speak>"
    )


def _format_azure_error(response: requests.Response, ssml: str) -> str:
    diag = {
        h: response.headers[h]
        for h in _AZURE_DIAGNOSTIC_HEADERS
        if h in response.headers
    }
    parts = [f"HTTP {response.status_code}"]
    if diag:
        parts.append("headers=" + ", ".join(f"{k}={v}" for k, v in diag.items()))
    body_preview = (response.text or "").strip()[:300]
    if body_preview:
        parts.append(f"body={body_preview}")
    # Truncated SSML helps diagnose voice-id / lang / escape issues.
    parts.append(f"ssml={ssml[:200]}")
    return "; ".join(parts)


class AzureTTS(TTSSynthesizer):
    provider_name = "azure"
    supports_concurrency = 8
    audio_format = "mp3"

    def __init__(
        self,
        *,
        api_key: str,
        region: str,
        config: TTSConfig,
        timeout_seconds: float = 60.0,
        session: requests.Session | None = None,
        output_format: str = "audio-48khz-192kbitrate-mono-mp3",
    ) -> None:
        self._api_key = api_key
        self._region = region
        self._config = config
        self._timeout = timeout_seconds
        self._session = session or requests.Session()
        self._output_format = output_format

    @classmethod
    def from_env(cls, env: EnvConfig, config: TTSConfig) -> "AzureTTS":
        assert env.tts_api_key and env.tts_region
        return cls(api_key=env.tts_api_key, region=env.tts_region, config=config)

    def synthesize(self, chunk: TextChunk, *, voice: VoiceConfig) -> bytes:
        if not voice.voice_id.strip():
            raise PermanentTTSError(
                "azure tts requires a non-empty voice_id (e.g. 'zh-CN-YunjianNeural')"
            )
        url = f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = _build_ssml(chunk.text, voice, xml_lang=_infer_xml_lang(voice.voice_id))
        try:
            response = self._session.post(
                url,
                headers={
                    "Ocp-Apim-Subscription-Key": self._api_key,
                    "X-Microsoft-OutputFormat": self._output_format,
                    "Content-Type": "application/ssml+xml",
                    "User-Agent": "lazy-podcast-mate",
                },
                data=ssml.encode("utf-8"),
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise TransientTTSError(f"network error: {exc}") from exc

        if response.status_code in _TRANSIENT_STATUS:
            raise TransientTTSError(f"azure tts {_format_azure_error(response, ssml)}")
        if response.status_code >= 400:
            raise PermanentTTSError(f"azure tts {_format_azure_error(response, ssml)}")

        if not response.content:
            raise PermanentTTSError("azure tts returned empty audio body")
        return response.content

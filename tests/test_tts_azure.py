"""Unit tests for the Azure TTS adapter."""

from __future__ import annotations

import pytest

from lazy_podcast_mate.chunking.models import TextChunk
from lazy_podcast_mate.config.schema import RetryConfig, TTSConfig
from lazy_podcast_mate.tts.azure import (
    AzureTTS,
    _build_ssml,
    _infer_xml_lang,
)
from lazy_podcast_mate.tts.base import VoiceConfig
from lazy_podcast_mate.tts.errors import PermanentTTSError, TransientTTSError


class _FakeResponse:
    def __init__(self, status_code: int, *, content: bytes = b"", text: str = "", headers: dict | None = None) -> None:
        self.status_code = status_code
        self.content = content
        self.text = text
        self.headers = headers or {}


class _ProgrammableSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def post(self, url, *, headers, data, timeout):
        self.calls.append({"url": url, "headers": headers, "data": data, "timeout": timeout})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _tts_cfg() -> TTSConfig:
    return TTSConfig(
        voice_id="zh-CN-YunjianNeural",
        rate=0.92,
        volume=1.0,
        concurrency=1,
        retry=RetryConfig(max_attempts=1, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0),
        failure_mode="strict",
    )


def _voice(voice_id: str = "zh-CN-YunjianNeural") -> VoiceConfig:
    return VoiceConfig(voice_id=voice_id, rate=0.92, volume=1.0)


def _chunk() -> TextChunk:
    return TextChunk(index=0, text="你好，世界。", char_count=6, hash="deadbeef")


def test_infer_xml_lang_from_standard_voice_ids():
    assert _infer_xml_lang("zh-CN-YunjianNeural") == "zh-CN"
    assert _infer_xml_lang("en-US-JennyNeural") == "en-US"
    assert _infer_xml_lang("ja-JP-NanamiNeural") == "ja-JP"


def test_infer_xml_lang_fallback_for_unknown_voice():
    # Legacy / custom / malformed voice ids fall back to zh-CN rather than 400ing.
    assert _infer_xml_lang("customvoice") == "zh-CN"
    assert _infer_xml_lang("") == "zh-CN"


def test_build_ssml_uses_inferred_lang_and_escapes_text():
    ssml = _build_ssml("hi & <there>", _voice("en-US-AndrewNeural"), xml_lang="en-US")
    assert 'xml:lang="en-US"' in ssml
    assert 'voice name="en-US-AndrewNeural"' in ssml
    assert "&amp;" in ssml and "&lt;there&gt;" in ssml


def test_synthesize_empty_voice_id_fails_fast():
    """The adapter must refuse to call Azure at all with an empty voice_id —
    otherwise every request 400s and the error body from Azure is empty,
    which is what bit the user in strict mode.
    """
    session = _ProgrammableSession([])  # no calls expected
    tts = AzureTTS(api_key="k", region="eastus", config=_tts_cfg(), session=session)  # type: ignore[arg-type]
    with pytest.raises(PermanentTTSError, match="non-empty voice_id"):
        tts.synthesize(_chunk(), voice=_voice(voice_id=""))
    assert session.calls == []


def test_synthesize_400_surfaces_azure_diagnostic_headers():
    """Azure leaves the body empty on many 400s — the real reason is in
    X-Microsoft-Reason / X-RequestId. The error message must include them
    so users can actually debug the failure.
    """
    session = _ProgrammableSession(
        [
            _FakeResponse(
                400,
                content=b"",
                text="",
                headers={
                    "X-Microsoft-Reason": "InvalidVoice",
                    "X-RequestId": "abc-123",
                },
            )
        ]
    )
    tts = AzureTTS(api_key="k", region="eastus", config=_tts_cfg(), session=session)  # type: ignore[arg-type]
    with pytest.raises(PermanentTTSError) as excinfo:
        tts.synthesize(_chunk(), voice=_voice())
    msg = str(excinfo.value)
    assert "HTTP 400" in msg
    assert "X-Microsoft-Reason=InvalidVoice" in msg
    assert "X-RequestId=abc-123" in msg
    # Includes truncated SSML so we can see what was actually sent.
    assert 'voice name="zh-CN-YunjianNeural"' in msg


def test_synthesize_429_is_transient_with_diagnostics():
    session = _ProgrammableSession(
        [_FakeResponse(429, text="", headers={"X-RequestId": "xyz"})]
    )
    tts = AzureTTS(api_key="k", region="eastus", config=_tts_cfg(), session=session)  # type: ignore[arg-type]
    with pytest.raises(TransientTTSError) as excinfo:
        tts.synthesize(_chunk(), voice=_voice())
    assert "HTTP 429" in str(excinfo.value)
    assert "X-RequestId=xyz" in str(excinfo.value)


def test_synthesize_happy_path_returns_mp3_bytes():
    mp3_bytes = b"\xff\xfb\x90" + b"\x00" * 100
    session = _ProgrammableSession([_FakeResponse(200, content=mp3_bytes)])
    tts = AzureTTS(api_key="k", region="eastus", config=_tts_cfg(), session=session)  # type: ignore[arg-type]
    out = tts.synthesize(_chunk(), voice=_voice())
    assert out == mp3_bytes
    # The outgoing request uses the inferred xml:lang from the voice id.
    sent_ssml = session.calls[0]["data"].decode("utf-8")
    assert 'xml:lang="zh-CN"' in sent_ssml
    assert 'voice name="zh-CN-YunjianNeural"' in sent_ssml

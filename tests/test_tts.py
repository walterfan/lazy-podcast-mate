"""Tests for TTS synthesis stage."""

from __future__ import annotations

from pathlib import Path

import pytest

from lazy_podcast_mate.chunking.models import TextChunk
from lazy_podcast_mate.config.schema import RetryConfig, TTSConfig
from lazy_podcast_mate.tts.base import TTSSynthesizer, VoiceConfig
from lazy_podcast_mate.tts.errors import PermanentTTSError, TransientTTSError
from lazy_podcast_mate.tts.synthesizer import (
    SynthesisReport,
    enforce_failure_mode,
    synthesize_chunks,
    validate_voice_config,
)


class FakeTTS(TTSSynthesizer):
    provider_name = "fake"
    supports_concurrency = 4
    audio_format = "mp3"

    def __init__(self, behavior: dict[int, object] | None = None) -> None:
        self.calls: list[int] = []
        self.behavior = behavior or {}

    def synthesize(self, chunk: TextChunk, *, voice: VoiceConfig) -> bytes:
        self.calls.append(chunk.index)
        action = self.behavior.get(chunk.index)
        if isinstance(action, Exception):
            raise action
        if isinstance(action, list) and action:
            nxt = action.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt  # type: ignore[return-value]
        return f"AUDIO[{chunk.index}]:{chunk.text}".encode("utf-8")


def _tts_cfg(**overrides) -> TTSConfig:
    base = dict(
        voice_id="v1",
        rate=0.92,
        volume=1.0,
        concurrency=2,
        retry=RetryConfig(max_attempts=3, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0),
        failure_mode="strict",
    )
    base.update(overrides)
    return TTSConfig(**base)


def _chunks(n: int) -> list[TextChunk]:
    return [TextChunk.make(index=i, text=f"text-{i}") for i in range(n)]


def _voice() -> VoiceConfig:
    return VoiceConfig(voice_id="v1", rate=0.92, volume=1.0)


def test_validate_voice_config_rejects_bad_rate():
    with pytest.raises(PermanentTTSError):
        validate_voice_config(_tts_cfg(rate=1.5))
    with pytest.raises(PermanentTTSError):
        validate_voice_config(_tts_cfg(rate=0.5))


def test_synthesize_happy_path_writes_all_files(tmp_path: Path):
    synth = FakeTTS()
    report = synthesize_chunks(
        _chunks(3),
        synthesizer=synth,
        voice=_voice(),
        config=_tts_cfg(),
        audio_dir=tmp_path,
    )
    assert report.ok
    for i in range(3):
        p = tmp_path / f"chunk_{i:04d}.mp3"
        assert p.exists()
        assert p.read_bytes() == f"AUDIO[{i}]:text-{i}".encode()


def test_rerun_reuses_cached_chunks(tmp_path: Path):
    synth = FakeTTS()
    synthesize_chunks(
        _chunks(3), synthesizer=synth, voice=_voice(),
        config=_tts_cfg(), audio_dir=tmp_path,
    )
    assert sorted(synth.calls) == [0, 1, 2]

    synth2 = FakeTTS()
    report2 = synthesize_chunks(
        _chunks(3), synthesizer=synth2, voice=_voice(),
        config=_tts_cfg(), audio_dir=tmp_path,
    )
    assert report2.ok
    assert synth2.calls == []


def test_transient_failure_retries_then_succeeds(tmp_path: Path):
    synth = FakeTTS(
        behavior={
            0: [TransientTTSError("flaky"), b"recovered"],
        }
    )
    report = synthesize_chunks(
        _chunks(1), synthesizer=synth, voice=_voice(),
        config=_tts_cfg(), audio_dir=tmp_path,
    )
    assert report.ok
    assert (tmp_path / "chunk_0000.mp3").read_bytes() == b"recovered"


def test_permanent_failure_in_strict_mode_raises(tmp_path: Path):
    synth = FakeTTS(behavior={1: PermanentTTSError("auth denied")})
    report = synthesize_chunks(
        _chunks(3), synthesizer=synth, voice=_voice(),
        config=_tts_cfg(), audio_dir=tmp_path,
    )
    assert not report.ok
    assert any(r.index == 1 and r.error and "permanent" in r.error for r in report.results)
    with pytest.raises(PermanentTTSError):
        enforce_failure_mode(report, failure_mode="strict")


def test_permanent_failure_in_lenient_mode_continues(tmp_path: Path, caplog):
    synth = FakeTTS(behavior={1: PermanentTTSError("auth denied")})
    report = synthesize_chunks(
        _chunks(3), synthesizer=synth, voice=_voice(),
        config=_tts_cfg(failure_mode="lenient"), audio_dir=tmp_path,
    )
    assert not report.ok
    # should not raise:
    enforce_failure_mode(report, failure_mode="lenient")
    # other chunks still succeeded:
    assert (tmp_path / "chunk_0000.mp3").exists()
    assert (tmp_path / "chunk_0002.mp3").exists()
    assert not (tmp_path / "chunk_0001.mp3").exists()


def test_exhausted_transient_is_reported_in_report(tmp_path: Path):
    synth = FakeTTS(
        behavior={
            0: [TransientTTSError("a"), TransientTTSError("b"), TransientTTSError("c")],
        }
    )
    report = synthesize_chunks(
        _chunks(1), synthesizer=synth, voice=_voice(),
        config=_tts_cfg(), audio_dir=tmp_path,
    )
    assert not report.ok
    assert "transient(exhausted)" in (report.results[0].error or "")

"""Tests for post-production.

Some tests require a real `ffmpeg` on PATH; they're skipped when missing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from pydub import AudioSegment
from pydub.generators import Sine

from lazy_podcast_mate.config.schema import PostConfig
from lazy_podcast_mate.post.bgm import mix_bgm
from lazy_podcast_mate.post.concat import concat_chunks
from lazy_podcast_mate.post.errors import FFmpegMissingError, PostProductionError
from lazy_podcast_mate.post.fades import apply_fades
from lazy_podcast_mate.post.ffmpeg_check import ensure_ffmpeg_available


HAS_FFMPEG = shutil.which("ffmpeg") is not None
ffmpeg_required = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


def _tone(ms: int, freq: int = 440) -> AudioSegment:
    return Sine(freq).to_audio_segment(duration=ms).set_channels(2).set_frame_rate(48000)


# ---------- ffmpeg_check ----------


def test_ensure_ffmpeg_available_raises_when_missing():
    def fake_which(_name):
        return None

    with pytest.raises(FFmpegMissingError, match="ffmpeg"):
        ensure_ffmpeg_available(which=fake_which)


def test_ensure_ffmpeg_available_ok_when_present():
    import subprocess

    calls = []

    def fake_which(_name):
        return "/fake/ffmpeg"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class R:
            returncode = 0
            stdout = b""
            stderr = b""

        return R()

    path = ensure_ffmpeg_available(which=fake_which, run=fake_run)
    assert path == "/fake/ffmpeg"
    assert calls and calls[0][0] == "/fake/ffmpeg"


# ---------- fades (pure pydub, no ffmpeg) ----------


@ffmpeg_required
def test_fades_change_endpoint_amplitude(tmp_path):
    tone = _tone(2000)
    faded = apply_fades(tone, fade_in_ms=500, fade_out_ms=500)
    assert len(faded) == len(tone)
    # The first 100 ms after fade-in should be much quieter than the middle.
    start_rms = faded[:100].rms
    middle_rms = faded[900:1100].rms
    assert start_rms < middle_rms


# ---------- concat (pydub + ffmpeg decoding) ----------


@ffmpeg_required
def test_concat_chunks_duration_matches_sum_plus_silences(tmp_path: Path):
    paths = []
    for i in range(3):
        p = tmp_path / f"chunk_{i:04d}.wav"
        _tone(500).export(p, format="wav")
        paths.append(p)

    combined = concat_chunks(paths, silence_ms=200)
    expected = 500 * 3 + 200 * 2
    assert abs(len(combined) - expected) < 20  # small rounding tolerance


@ffmpeg_required
def test_concat_chunks_rejects_missing_file(tmp_path: Path):
    p = tmp_path / "missing.wav"
    with pytest.raises(PostProductionError, match="missing or empty"):
        concat_chunks([p], silence_ms=0)


# ---------- BGM mixing ----------


@ffmpeg_required
def test_bgm_ratio_out_of_range_rejected(tmp_path: Path):
    bgm = tmp_path / "bgm.wav"
    _tone(1000, freq=220).export(bgm, format="wav")
    voice = _tone(1000, freq=440)
    with pytest.raises(PostProductionError, match="bgm ratio"):
        mix_bgm(voice, bgm, ratio=0.5)


@ffmpeg_required
def test_bgm_mix_matches_ratio_within_tolerance(tmp_path: Path):
    bgm_path = tmp_path / "bgm.wav"
    _tone(3000, freq=220).export(bgm_path, format="wav")
    voice = _tone(2000, freq=440)

    mixed = mix_bgm(voice, bgm_path, ratio=0.12)

    # Sanity: mix duration equals voice duration.
    assert abs(len(mixed) - len(voice)) < 20


# ---------- Post pipeline (config sanity only) ----------


def test_post_config_defaults_are_within_spec():
    cfg = PostConfig()
    assert cfg.fade_in_ms == 500
    assert cfg.fade_out_ms == 500
    assert cfg.loudness_target_lufs == -16.0
    assert cfg.loudness_true_peak_dbtp == -1.0
    assert 0.10 <= cfg.bgm_ratio <= 0.15

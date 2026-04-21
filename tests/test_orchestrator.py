"""Integration tests for the pipeline orchestrator (fake LLM + fake TTS).

These exercise checkpoint resume, `--force-stage`, and end-to-end flow
without calling any real networked provider. Some variants depend on ffmpeg;
they skip cleanly when ffmpeg is unavailable.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from lazy_podcast_mate.chunking.models import TextChunk
from lazy_podcast_mate.config.env import EnvConfig
from lazy_podcast_mate.config.schema import (
    AppConfig,
    ChunkingConfig,
    CleaningConfig,
    ID3Config,
    LoggingConfig,
    OutputConfig,
    PostConfig,
    RetryConfig,
    ScriptConfig,
    TTSConfig,
)
from lazy_podcast_mate.orchestrator.checkpoints import Stage, has_valid_checkpoint, RunPaths
from lazy_podcast_mate.orchestrator.runner import RunOptions, run_pipeline
from lazy_podcast_mate.script import registry as script_registry
from lazy_podcast_mate.script.base import ArticleMetadata, RewriteResult
from lazy_podcast_mate.tts import registry as tts_registry
from lazy_podcast_mate.tts.base import VoiceConfig

HAS_FFMPEG = shutil.which("ffmpeg") is not None
ffmpeg_required = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


class _FakeRewriter:
    provider_name = "fake_llm"

    def __init__(self, script: str = "Opening paragraph.\n\nBody paragraph one.\n\nClosing paragraph.") -> None:
        self.script = script
        self.calls = 0

    def rewrite(self, cleaned_text: str, *, metadata: ArticleMetadata) -> RewriteResult:
        self.calls += 1
        return RewriteResult(
            script=self.script, provider=self.provider_name, model="fake-1", prompt_version="v1"
        )


class _FakeTTS:
    provider_name = "fake_tts"
    supports_concurrency = 2
    audio_format = "wav"

    def __init__(self) -> None:
        self.calls: list[int] = []

    def synthesize(self, chunk: TextChunk, *, voice: VoiceConfig) -> bytes:
        self.calls.append(chunk.index)
        # Minimal valid WAV header + 100 ms of silence at 8 kHz mono 16-bit.
        # Easier: use pydub to synthesize silence, but to avoid ffmpeg here
        # we return the raw bytes of a pre-encoded tiny WAV generated below.
        return _tiny_wav_bytes()


def _tiny_wav_bytes() -> bytes:
    """Return the bytes of a minimal valid WAV containing a quiet 440 Hz tone.

    Must be non-silent so the ffmpeg loudnorm pass that the post-production
    stage runs can actually measure an integrated loudness — silent inputs
    produce ``input_i = "-inf"`` and ffmpeg rejects the pass-2 filter.
    Duration is kept very short (400 ms) so tests stay fast.
    """
    import math
    import struct

    sample_rate = 8000
    ms = 400
    num_samples = sample_rate * ms // 1000
    # Quiet sine wave at ~-20 dBFS peak; plenty for loudnorm to measure.
    amplitude = int(0.1 * 32767)
    frequency = 440.0
    two_pi_f_over_sr = 2 * math.pi * frequency / sample_rate
    samples = bytearray()
    for n in range(num_samples):
        sample = int(amplitude * math.sin(two_pi_f_over_sr * n))
        samples.extend(struct.pack("<h", sample))
    riff = b"RIFF"
    wave = b"WAVE"
    fmt_chunk = (
        b"fmt "
        + struct.pack("<I", 16)
        + struct.pack("<H", 1)
        + struct.pack("<H", 1)
        + struct.pack("<I", sample_rate)
        + struct.pack("<I", sample_rate * 2)
        + struct.pack("<H", 2)
        + struct.pack("<H", 16)
    )
    data_chunk = b"data" + struct.pack("<I", len(samples)) + bytes(samples)
    size = 4 + len(fmt_chunk) + len(data_chunk)
    return riff + struct.pack("<I", size) + wave + fmt_chunk + data_chunk


def _fast_retry() -> RetryConfig:
    return RetryConfig(max_attempts=2, initial_delay_seconds=0, backoff_factor=1, max_delay_seconds=0)


def _app_config(tmp_path: Path, with_bgm: bool = False) -> AppConfig:
    return AppConfig(
        cleaning=CleaningConfig(max_input_bytes=1_000_000, terms=[]),
        chunking=ChunkingConfig(max_chars=200, inter_chunk_silence_ms=50),
        script=ScriptConfig(prompt_version="v1", token_budget=100_000, retry=_fast_retry()),
        tts=TTSConfig(voice_id="v1", rate=0.92, volume=1.0, concurrency=2, retry=_fast_retry(), failure_mode="strict"),
        post=PostConfig(
            fade_in_ms=50, fade_out_ms=50,
            bgm_path="" if not with_bgm else str(tmp_path / "bgm.wav"),
            bgm_ratio=0.12,
            loudness_target_lufs=-16.0,
            loudness_true_peak_dbtp=-1.0,
            loudness_tolerance_lu=5.0,  # relax for short silent samples
            denoise=False,
        ),
        output=OutputConfig(
            directory=str(tmp_path / "out"),
            filename_pattern="{date}-{slug}.mp3",
            on_existing="suffix",
            id3=ID3Config(artist="Tester", album="Demo"),
            run_data_directory=str(tmp_path / "runs"),
            history_file=str(tmp_path / "history.jsonl"),
        ),
        logging=LoggingConfig(level="INFO"),
    )


def _env() -> EnvConfig:
    return EnvConfig(
        llm_provider="fake", llm_api_key="k", llm_base_url="x", llm_model="m",
        tts_provider="fake", tts_api_key="k", tts_region=None, tts_app_id=None,
        tts_cluster=None, tts_base_url=None, lpm_config_path=None,
    )


@pytest.fixture()
def patched_providers(monkeypatch):
    fake_rewriter = _FakeRewriter()
    fake_tts = _FakeTTS()
    monkeypatch.setattr(script_registry, "build_rewriter", lambda env, cfg: fake_rewriter)
    monkeypatch.setattr(tts_registry, "build_synthesizer", lambda env, cfg: fake_tts)
    # runner imports these names into its own namespace, so patch those too
    from lazy_podcast_mate.orchestrator import runner
    monkeypatch.setattr(runner, "build_rewriter", lambda env, cfg: fake_rewriter)
    monkeypatch.setattr(runner, "build_synthesizer", lambda env, cfg: fake_tts)
    return fake_rewriter, fake_tts


@ffmpeg_required
def test_end_to_end_pipeline_produces_mp3(tmp_path: Path, patched_providers):
    rewriter, tts = patched_providers
    article = tmp_path / "article.md"
    article.write_text(
        "# Episode Title\n\nParagraph one body text.\n\nParagraph two body text.\n",
        encoding="utf-8",
    )
    cfg = _app_config(tmp_path)
    options = RunOptions(
        input_path=article,
        run_id="test-run-1",
        run_dir=Path(cfg.output.run_data_directory) / "test-run-1",
    )
    outcome = run_pipeline(options, config=cfg, env=_env())
    assert outcome.status == "success", outcome.error
    assert outcome.output_path is not None
    assert outcome.output_path.exists()

    # ID3 tags round-trip
    from mutagen.id3 import ID3
    tags = ID3(outcome.output_path)
    assert tags.getall("TIT2")[0].text[0] == "Episode Title"
    assert tags.getall("TPE1")[0].text[0] == "Tester"

    # history entry written
    hist = Path(cfg.output.history_file).read_text(encoding="utf-8").splitlines()
    assert len(hist) == 1
    parsed = json.loads(hist[0])
    assert parsed["status"] == "success"
    assert parsed["run_id"] == "test-run-1"

    assert rewriter.calls == 1


@ffmpeg_required
def test_rerun_reuses_checkpoints(tmp_path: Path, patched_providers):
    rewriter, tts = patched_providers
    article = tmp_path / "article.md"
    article.write_text("# T\n\nBody.\n\nMore body.\n", encoding="utf-8")
    cfg = _app_config(tmp_path)
    options = RunOptions(
        input_path=article,
        run_id="rerun-1",
        run_dir=Path(cfg.output.run_data_directory) / "rerun-1",
    )
    out1 = run_pipeline(options, config=cfg, env=_env())
    assert out1.status == "success"
    first_llm_calls = rewriter.calls
    first_tts_calls = len(tts.calls)

    # Delete one chunk audio — the TTS stage should resynth only that one.
    paths = RunPaths(root=options.run_dir)
    chunk_audio = next(paths.audio_dir.glob("chunk_*.wav"))
    chunk_audio.unlink()

    out2 = run_pipeline(options, config=cfg, env=_env())
    assert out2.status == "success"
    # LLM was NOT called again (script.md still present).
    assert rewriter.calls == first_llm_calls
    # Only one additional TTS call
    assert len(tts.calls) == first_tts_calls + 1


@ffmpeg_required
def test_force_stage_script_reruns_everything_from_script(tmp_path: Path, patched_providers):
    rewriter, tts = patched_providers
    article = tmp_path / "article.md"
    article.write_text("# T\n\nBody.\n", encoding="utf-8")
    cfg = _app_config(tmp_path)
    options = RunOptions(
        input_path=article,
        run_id="force-1",
        run_dir=Path(cfg.output.run_data_directory) / "force-1",
    )
    out1 = run_pipeline(options, config=cfg, env=_env())
    assert out1.status == "success"
    before_llm = rewriter.calls
    before_tts = len(tts.calls)

    options2 = RunOptions(
        input_path=article,
        run_id="force-1",
        run_dir=options.run_dir,
        force_stage=Stage.SCRIPT,
    )
    out2 = run_pipeline(options2, config=cfg, env=_env())
    assert out2.status == "success"
    assert rewriter.calls == before_llm + 1
    # All chunks got re-synthesised too.
    assert len(tts.calls) > before_tts


def test_checkpoint_helpers(tmp_path: Path):
    paths = RunPaths(root=tmp_path / "r")
    paths.root.mkdir()
    assert not has_valid_checkpoint(Stage.INGESTION, paths)
    paths.article_json.write_text(json.dumps({"article": {"title": "t", "body": "b", "source_path": "/x", "source_format": "markdown", "detected_encoding": "utf-8"}}), encoding="utf-8")
    assert has_valid_checkpoint(Stage.INGESTION, paths)
    assert not has_valid_checkpoint(Stage.CLEANING, paths)
    data = json.loads(paths.article_json.read_text(encoding="utf-8"))
    data["cleaned_text"] = "cleaned"
    paths.article_json.write_text(json.dumps(data), encoding="utf-8")
    assert has_valid_checkpoint(Stage.CLEANING, paths)
    assert not has_valid_checkpoint(Stage.SCRIPT, paths)

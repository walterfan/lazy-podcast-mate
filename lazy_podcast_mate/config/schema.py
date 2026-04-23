"""Typed schema for `config.yaml`."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class TermEntry:
    from_: str
    to: str
    case_sensitive: bool = True
    word_boundary: bool = True


@dataclass(frozen=True)
class CleaningConfig:
    max_input_bytes: int = 5_000_000
    terms: list[TermEntry] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkingConfig:
    max_chars: int = 800
    inter_chunk_silence_ms: int = 250


@dataclass(frozen=True)
class RetryConfig:
    max_attempts: int = 4
    initial_delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 30.0


@dataclass(frozen=True)
class ScriptConfig:
    prompt_version: str = "v2"
    token_budget: int = 12000
    retry: RetryConfig = field(default_factory=RetryConfig)
    request_timeout_seconds: float = 180.0
    stream: bool = False
    # Sampling parameters. Set any of these to ``None`` (YAML ``null`` or
    # the literal string ``"omit"``) to drop the field from the request body
    # entirely — required for reasoning-tier models (e.g. Anthropic claude-opus-4-7,
    # OpenAI o1/o3) that reject these parameters.
    temperature: float | None = 0.5
    top_p: float | None = None
    max_tokens: int | None = None


FailureMode = Literal["strict", "lenient"]


@dataclass(frozen=True)
class TTSConfig:
    voice_id: str = ""
    rate: float = 0.92
    volume: float = 1.0
    concurrency: int = 4
    retry: RetryConfig = field(default_factory=RetryConfig)
    failure_mode: FailureMode = "strict"


@dataclass(frozen=True)
class PostConfig:
    fade_in_ms: int = 500
    fade_out_ms: int = 500
    bgm_path: str = ""
    bgm_ratio: float = 0.12
    loudness_target_lufs: float = -16.0
    loudness_true_peak_dbtp: float = -1.0
    loudness_tolerance_lu: float = 1.0
    denoise: bool = True


OnExisting = Literal["error", "suffix"]


@dataclass(frozen=True)
class ID3Config:
    artist: str = "Lazy Podcast Mate"
    album: str = "Lazy Podcast Mate"


@dataclass(frozen=True)
class OutputConfig:
    directory: str = "./data/output"
    filename_pattern: str = "{date}-{slug}.mp3"
    on_existing: OnExisting = "suffix"
    id3: ID3Config = field(default_factory=ID3Config)
    run_data_directory: str = "./data/runs"
    history_file: str = "./data/history.jsonl"


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"


@dataclass(frozen=True)
class AppConfig:
    """Merged, validated configuration used by all stages."""

    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    script: ScriptConfig = field(default_factory=ScriptConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    post: PostConfig = field(default_factory=PostConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

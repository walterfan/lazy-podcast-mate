"""Drive chunk-level synthesis with concurrency, retry, and resumability."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..chunking.models import TextChunk
from ..config.schema import TTSConfig
from .base import TTSSynthesizer, VoiceConfig
from .errors import PermanentTTSError, TransientTTSError
from .retry import retry_tts_call

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChunkResult:
    index: int
    path: Path | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.path is not None


@dataclass(frozen=True)
class SynthesisReport:
    results: list[ChunkResult]

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def failed(self) -> list[ChunkResult]:
        return [r for r in self.results if not r.ok]


def validate_voice_config(config: TTSConfig) -> None:
    """Hard-fail if the voice config is out of bounds (belt-and-braces; the
    config loader already enforces this)."""
    if not (0.9 <= config.rate <= 0.95):
        raise PermanentTTSError(
            f"tts.rate must be within [0.9, 0.95], got {config.rate}"
        )
    if config.volume <= 0:
        raise PermanentTTSError(f"tts.volume must be > 0, got {config.volume}")
    if config.concurrency <= 0:
        raise PermanentTTSError(
            f"tts.concurrency must be > 0, got {config.concurrency}"
        )


def _chunk_path(audio_dir: Path, chunk: TextChunk, ext: str) -> Path:
    return audio_dir / f"chunk_{chunk.index:04d}.{ext}"


def _synthesize_one(
    synthesizer: TTSSynthesizer,
    chunk: TextChunk,
    voice: VoiceConfig,
    audio_dir: Path,
    config: TTSConfig,
) -> ChunkResult:
    target = _chunk_path(audio_dir, chunk, synthesizer.audio_format)
    if target.exists() and target.stat().st_size > 0:
        log.debug("reusing cached chunk audio: %s", target)
        return ChunkResult(index=chunk.index, path=target)

    def call() -> bytes:
        return synthesizer.synthesize(chunk, voice=voice)

    try:
        data = retry_tts_call(
            call,
            config=config.retry,
            label=f"tts.chunk[{chunk.index}]",
        )
    except TransientTTSError as exc:
        return ChunkResult(
            index=chunk.index, path=None, error=f"transient(exhausted): {exc}"
        )
    except PermanentTTSError as exc:
        return ChunkResult(index=chunk.index, path=None, error=f"permanent: {exc}")

    audio_dir.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".partial")
    tmp.write_bytes(data)
    tmp.replace(target)
    return ChunkResult(index=chunk.index, path=target)


def synthesize_chunks(
    chunks: Iterable[TextChunk],
    *,
    synthesizer: TTSSynthesizer,
    voice: VoiceConfig,
    config: TTSConfig,
    audio_dir: Path,
) -> SynthesisReport:
    """Run synthesis for all chunks; return a report with per-chunk outcomes.

    Chunks with existing valid cache files are reused and not re-synthesised.
    Transient failures are retried up to `config.retry.max_attempts` per chunk.
    Failure-mode enforcement (strict vs lenient) is the caller's responsibility.
    """
    validate_voice_config(config)

    chunk_list = list(chunks)
    worker_count = min(config.concurrency, synthesizer.supports_concurrency, len(chunk_list)) or 1

    results: dict[int, ChunkResult] = {}
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _synthesize_one, synthesizer, chunk, voice, audio_dir, config
            ): chunk.index
            for chunk in chunk_list
        }
        for fut in as_completed(futures):
            result = fut.result()
            results[result.index] = result

    ordered = [results[c.index] for c in chunk_list]
    return SynthesisReport(results=ordered)


def enforce_failure_mode(
    report: SynthesisReport,
    *,
    failure_mode: str,
) -> None:
    """Raise if strict-mode and any chunk failed; log a warning otherwise."""
    if report.ok:
        return
    if failure_mode == "strict":
        failed = ", ".join(f"#{r.index}({r.error})" for r in report.failed)
        raise PermanentTTSError(f"tts chunks failed in strict mode: {failed}")
    # lenient: record each failure
    for r in report.failed:
        log.warning("tts chunk %d failed (lenient mode): %s", r.index, r.error)

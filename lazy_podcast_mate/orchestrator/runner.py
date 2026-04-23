"""Stage runner: walk every stage, skip if checkpoint valid."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from ..chunking.chunker import chunk_script
from ..chunking.models import load_manifest, save_manifest
from ..cleaning.cleaner import clean_article
from ..config.env import EnvConfig
from ..config.schema import AppConfig
from ..ingestion.loader import load_article
from ..ingestion.models import Article
from ..output.filename import render_filename
from ..output.history import HistoryEntry, append_history, iso_now
from ..output.id3 import write_id3_tags
from ..output.shownotes import ShowNotesContext, write_show_notes
from ..output.writer import place_output
from ..post.ffmpeg_check import ensure_ffmpeg_available
from ..post.pipeline import run_post_production
from ..script.base import ArticleMetadata
from ..script.registry import build_rewriter
from ..script.stage import run_script_stage
from ..tts.base import VoiceConfig
from ..tts.registry import build_synthesizer
from ..tts.synthesizer import enforce_failure_mode, synthesize_chunks
from .checkpoints import (
    RunPaths,
    Stage,
    has_valid_checkpoint,
    invalidate_from,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    output_path: Path | None
    status: str  # "success" | "failed"
    error: str | None = None


@dataclass(frozen=True)
class RunOptions:
    input_path: Path
    run_id: str
    run_dir: Path
    force_stage: Stage | None = None
    failure_mode_override: str | None = None
    dry_run_script: bool = False


def _write_article_json(paths: RunPaths, article: Article, cleaned_text: str | None = None) -> None:
    existing: dict = {}
    if paths.article_json.exists():
        try:
            existing = json.loads(paths.article_json.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    existing["article"] = article.to_dict()
    if cleaned_text is not None:
        existing["cleaned_text"] = cleaned_text
    paths.article_json.parent.mkdir(parents=True, exist_ok=True)
    paths.article_json.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _read_article_json(paths: RunPaths) -> tuple[Article, str | None]:
    data = json.loads(paths.article_json.read_text(encoding="utf-8"))
    article = Article.from_dict(data["article"])
    cleaned = data.get("cleaned_text")
    return article, cleaned


def run_pipeline(
    options: RunOptions,
    *,
    config: AppConfig,
    env: EnvConfig,
) -> RunOutcome:
    paths = RunPaths(root=options.run_dir)
    paths.root.mkdir(parents=True, exist_ok=True)

    started = time.time()
    started_iso = iso_now()

    if options.force_stage is not None:
        log.info("force-stage: invalidating from %s onwards", options.force_stage.value)
        invalidate_from(options.force_stage, paths)

    history_path = Path(config.output.history_file).expanduser()
    outcome: RunOutcome

    llm_provider = env.llm_provider
    llm_model = env.llm_model
    tts_provider = env.tts_provider
    tts_voice_id = config.tts.voice_id
    output_path: Path | None = None
    streamed_script_output = False

    try:
        # -------- Ingestion + cleaning --------
        if has_valid_checkpoint(Stage.CLEANING, paths):
            log.info("stage.ingestion+cleaning: checkpoint valid, skipping")
            article, cleaned_text = _read_article_json(paths)
            assert cleaned_text is not None
        else:
            log.info("stage.ingestion: reading %s", options.input_path)
            article = load_article(
                options.input_path, max_bytes=config.cleaning.max_input_bytes
            )
            _write_article_json(paths, article)
            log.info("stage.cleaning: cleaning article text")
            cleaned_text = clean_article(article, config.cleaning)
            _write_article_json(paths, article, cleaned_text)

        # -------- Script rewriting --------
        if has_valid_checkpoint(Stage.SCRIPT, paths):
            log.info("stage.script: checkpoint valid, skipping")
            script_text = paths.script_md.read_text(encoding="utf-8")
        else:
            log.info("stage.script: calling LLM (%s / %s)", llm_provider, llm_model)
            rewriter = build_rewriter(env, config.script)
            on_delta = None
            if (
                options.dry_run_script
                and config.script.stream
                and llm_provider in {"openai_compatible", "domestic"}
            ):
                streamed_script_output = True

                def _print_delta(delta: str) -> None:
                    print(delta, end="", flush=True)

                on_delta = _print_delta
            result = run_script_stage(
                cleaned_text,
                metadata=ArticleMetadata(
                    title=article.title, source_format=article.source_format
                ),
                rewriter=rewriter,
                token_budget=config.script.token_budget,
                on_delta=on_delta,
            )
            script_text = result.script
            paths.script_md.write_text(script_text, encoding="utf-8")
            log.info("stage.script: script written to %s", paths.script_md)
            if streamed_script_output:
                print()

        if options.dry_run_script:
            log.info("dry-run-script: stopping after script stage")
            if not streamed_script_output:
                print(script_text)
            return RunOutcome(
                run_id=options.run_id, output_path=None, status="success"
            )

        # -------- Chunking --------
        if has_valid_checkpoint(Stage.CHUNKING, paths):
            log.info("stage.chunking: checkpoint valid, skipping")
            chunks = load_manifest(paths.chunks_json)
        else:
            log.info("stage.chunking: splitting script into chunks")
            chunks = chunk_script(script_text, max_chars=config.chunking.max_chars)
            save_manifest(chunks, paths.chunks_json)
            log.info("stage.chunking: %d chunks written to %s", len(chunks), paths.chunks_json)

        # -------- TTS --------
        if has_valid_checkpoint(Stage.TTS, paths):
            log.info("stage.tts: all chunk audio present, skipping")
        else:
            log.info("stage.tts: synthesising %d chunks", len(chunks))
            synthesizer = build_synthesizer(env, config.tts)
            voice = VoiceConfig(
                voice_id=config.tts.voice_id,
                rate=config.tts.rate,
                volume=config.tts.volume,
            )
            report = synthesize_chunks(
                chunks,
                synthesizer=synthesizer,
                voice=voice,
                config=config.tts,
                audio_dir=paths.audio_dir,
            )
            failure_mode = options.failure_mode_override or config.tts.failure_mode
            enforce_failure_mode(report, failure_mode=failure_mode)

        # -------- Post-production --------
        ensure_ffmpeg_available()
        if has_valid_checkpoint(Stage.POST, paths):
            log.info("stage.post: final.mp3 exists, skipping")
        else:
            audio_paths = [
                next(
                    p
                    for p in (
                        paths.audio_dir / f"chunk_{c.index:04d}.mp3",
                        paths.audio_dir / f"chunk_{c.index:04d}.wav",
                    )
                    if p.exists()
                )
                for c in chunks
            ]
            log.info("stage.post: running post-production")
            run_post_production(
                audio_paths,
                config=config.post,
                inter_chunk_silence_ms=config.chunking.inter_chunk_silence_ms,
                output_path=paths.final_mp3,
                work_dir=paths.post_workdir,
            )

        # -------- Output --------
        log.info("stage.output: placing final MP3 + writing ID3 tags")
        filename = render_filename(
            config.output.filename_pattern,
            title=article.title,
            run_id=options.run_id,
        )
        output_path = place_output(paths.final_mp3, filename, config=config.output)
        write_id3_tags(
            output_path,
            title=article.title,
            config=config.output.id3,
            comment=f"run_id={options.run_id}",
        )
        log.info("stage.output: wrote %s", output_path)

        # Show-notes are best-effort: if we cannot write them we still return
        # a successful run, because the MP3 (the primary deliverable) is
        # already in place.
        try:
            notes_path = write_show_notes(
                ShowNotesContext(
                    title=article.title,
                    source_path=str(options.input_path),
                    run_id=options.run_id,
                    article=article,
                    audio_filename=output_path.name,
                ),
                audio_path=output_path,
                config=config.output,
            )
            log.info("stage.output: wrote show notes %s", notes_path)
        except Exception:
            log.exception("stage.output: failed to write show notes (non-fatal)")

        outcome = RunOutcome(
            run_id=options.run_id, output_path=output_path, status="success"
        )
    except Exception as exc:  # noqa: BLE001 — final catch-all for history
        log.exception("pipeline failed: %s", exc)
        outcome = RunOutcome(
            run_id=options.run_id,
            output_path=None,
            status="failed",
            error=f"{type(exc).__name__}: {exc}",
        )

    ended_iso = iso_now()
    try:
        append_history(
            history_path,
            HistoryEntry(
                run_id=options.run_id,
                source_path=str(options.input_path),
                output_path=str(outcome.output_path) if outcome.output_path else None,
                status=outcome.status,
                started_at=started_iso,
                ended_at=ended_iso,
                duration_seconds=round(time.time() - started, 2),
                llm_provider=llm_provider,
                llm_model=llm_model,
                tts_provider=tts_provider,
                tts_voice_id=tts_voice_id,
                error=outcome.error,
            ),
        )
    except Exception:
        log.exception("failed to append history line")

    return outcome

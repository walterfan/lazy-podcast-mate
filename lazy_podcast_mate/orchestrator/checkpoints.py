"""Per-stage checkpoint contracts and validators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..chunking.models import TextChunk, load_manifest


class Stage(str, Enum):
    INGESTION = "ingestion"
    CLEANING = "cleaning"
    SCRIPT = "script"
    CHUNKING = "chunking"
    TTS = "tts"
    POST = "post"
    OUTPUT = "output"


STAGE_ORDER: list[Stage] = [
    Stage.INGESTION,
    Stage.CLEANING,
    Stage.SCRIPT,
    Stage.CHUNKING,
    Stage.TTS,
    Stage.POST,
    Stage.OUTPUT,
]


@dataclass(frozen=True)
class RunPaths:
    root: Path

    @property
    def article_json(self) -> Path:
        return self.root / "article.json"

    @property
    def script_md(self) -> Path:
        return self.root / "script.md"

    @property
    def chunks_json(self) -> Path:
        return self.root / "chunks.json"

    @property
    def audio_dir(self) -> Path:
        return self.root / "audio"

    @property
    def final_mp3(self) -> Path:
        return self.root / "final.mp3"

    @property
    def run_log(self) -> Path:
        return self.root / "run.log"

    @property
    def post_workdir(self) -> Path:
        return self.root / "post"


def article_checkpoint_valid(paths: RunPaths) -> bool:
    p = paths.article_json
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return "article" in data
    except Exception:
        return False


def cleaning_checkpoint_valid(paths: RunPaths) -> bool:
    p = paths.article_json
    if not article_checkpoint_valid(paths):
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return "cleaned_text" in data and bool(data["cleaned_text"])
    except Exception:
        return False


def script_checkpoint_valid(paths: RunPaths) -> bool:
    p = paths.script_md
    return p.exists() and p.stat().st_size > 0


def chunking_checkpoint_valid(paths: RunPaths) -> bool:
    p = paths.chunks_json
    if not p.exists() or p.stat().st_size == 0:
        return False
    try:
        load_manifest(p)
        return True
    except Exception:
        return False


def tts_checkpoint_valid(paths: RunPaths) -> bool:
    if not chunking_checkpoint_valid(paths):
        return False
    chunks: list[TextChunk] = load_manifest(paths.chunks_json)
    if not paths.audio_dir.exists():
        return False
    for chunk in chunks:
        # Accept either mp3 or wav.
        found = False
        for ext in ("mp3", "wav"):
            f = paths.audio_dir / f"chunk_{chunk.index:04d}.{ext}"
            if f.exists() and f.stat().st_size > 0:
                found = True
                break
        if not found:
            return False
    return True


def post_checkpoint_valid(paths: RunPaths) -> bool:
    p = paths.final_mp3
    return p.exists() and p.stat().st_size > 0


def has_valid_checkpoint(stage: Stage, paths: RunPaths) -> bool:
    if stage is Stage.INGESTION:
        return article_checkpoint_valid(paths)
    if stage is Stage.CLEANING:
        return cleaning_checkpoint_valid(paths)
    if stage is Stage.SCRIPT:
        return script_checkpoint_valid(paths)
    if stage is Stage.CHUNKING:
        return chunking_checkpoint_valid(paths)
    if stage is Stage.TTS:
        return tts_checkpoint_valid(paths)
    if stage is Stage.POST:
        return post_checkpoint_valid(paths)
    if stage is Stage.OUTPUT:
        return False  # OUTPUT is never cached; it always re-writes the history line.
    raise ValueError(f"unknown stage: {stage!r}")


def invalidate_from(stage: Stage, paths: RunPaths) -> None:
    """Remove all checkpoint artefacts for `stage` and every later stage.

    Used by `--force-stage`.
    """
    if paths.root.exists() is False:
        return

    idx = STAGE_ORDER.index(stage)
    stages_to_clear = STAGE_ORDER[idx:]

    for s in stages_to_clear:
        if s is Stage.INGESTION or s is Stage.CLEANING:
            if paths.article_json.exists():
                paths.article_json.unlink()
        elif s is Stage.SCRIPT:
            if paths.script_md.exists():
                paths.script_md.unlink()
        elif s is Stage.CHUNKING:
            if paths.chunks_json.exists():
                paths.chunks_json.unlink()
        elif s is Stage.TTS:
            if paths.audio_dir.exists():
                for f in paths.audio_dir.iterdir():
                    if f.is_file():
                        f.unlink()
        elif s is Stage.POST:
            if paths.final_mp3.exists():
                paths.final_mp3.unlink()
        elif s is Stage.OUTPUT:
            pass  # handled by `output` stage itself

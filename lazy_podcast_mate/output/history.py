"""Append one JSON line per run to the history log."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class HistoryEntry:
    run_id: str
    source_path: str
    output_path: str | None
    status: str
    started_at: str
    ended_at: str
    duration_seconds: float
    llm_provider: str | None
    llm_model: str | None
    tts_provider: str | None
    tts_voice_id: str | None
    error: str | None = None
    extra: dict = field(default_factory=dict)

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def append_history(path: Path, entry: HistoryEntry) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.to_json_line())
        fh.write("\n")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

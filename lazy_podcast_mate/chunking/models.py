"""Chunking data model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    char_count: int = field(default=0)
    hash: str = field(default="")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def make(cls, index: int, text: str) -> "TextChunk":
        return cls(
            index=index,
            text=text,
            char_count=len(text),
            hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )


def save_manifest(chunks: list[TextChunk], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"chunks": [c.to_dict() for c in chunks]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_manifest(path: Path) -> list[TextChunk]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        TextChunk(
            index=int(c["index"]),
            text=str(c["text"]),
            char_count=int(c["char_count"]),
            hash=str(c["hash"]),
        )
        for c in data["chunks"]
    ]

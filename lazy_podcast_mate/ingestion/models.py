"""Dataclasses for ingested articles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

SourceFormat = Literal["markdown", "html", "text"]
PlaceholderKind = Literal["code", "image", "table"]


@dataclass(frozen=True)
class Link:
    """A hyperlink extracted from the source article.

    The anchor text is preserved in the spoken body; the URL is dropped from
    the spoken script and surfaced via show-notes instead.
    """

    text: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Link":
        return cls(text=str(data["text"]), url=str(data["url"]))


@dataclass(frozen=True)
class PlaceholderRef:
    """Reference to a non-spoken element (code / image / table) that was
    replaced by a short label in the body text.

    - ``token`` is the internal id we write into the ingestion body; the
      cleaner substitutes it for ``label`` before the LLM sees the text.
    - ``label`` is the short natural-language stand-in that the LLM reads
      and decides whether to mention (e.g. ``[此处有一段 Python 代码示例]``).
    - ``detail`` preserves the original content so show-notes can reproduce
      it verbatim (e.g. the full fenced code block).
    """

    kind: PlaceholderKind
    token: str
    label: str
    detail: str
    language: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PlaceholderRef":
        return cls(
            kind=data["kind"],
            token=str(data["token"]),
            label=str(data["label"]),
            detail=str(data["detail"]),
            language=data.get("language"),
        )


@dataclass(frozen=True)
class Article:
    title: str
    body: str
    source_path: str
    source_format: SourceFormat
    detected_encoding: str
    links: list[Link] = field(default_factory=list)
    placeholders: list[PlaceholderRef] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        return cls(
            title=str(data["title"]),
            body=str(data["body"]),
            source_path=str(data["source_path"]),
            source_format=data["source_format"],
            detected_encoding=str(data["detected_encoding"]),
            links=[Link.from_dict(entry) for entry in data.get("links", [])],
            placeholders=[
                PlaceholderRef.from_dict(entry)
                for entry in data.get("placeholders", [])
            ],
        )

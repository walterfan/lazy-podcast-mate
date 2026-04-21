"""Write ID3v2 tags on the exported MP3."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mutagen.id3 import COMM, ID3, ID3NoHeaderError, TALB, TDRC, TIT2, TPE1

from ..config.schema import ID3Config


def write_id3_tags(
    mp3_path: Path,
    *,
    title: str,
    config: ID3Config,
    comment: str = "",
    release_date: datetime | None = None,
) -> None:
    try:
        tags = ID3(mp3_path)
    except ID3NoHeaderError:
        tags = ID3()

    date = (release_date or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("TALB")
    tags.delall("TDRC")
    tags.delall("COMM")
    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=config.artist))
    tags.add(TALB(encoding=3, text=config.album))
    tags.add(TDRC(encoding=3, text=date))
    if comment:
        tags.add(COMM(encoding=3, lang="eng", desc="", text=comment))
    tags.save(mp3_path, v2_version=3)

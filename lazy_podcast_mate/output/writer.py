"""Place the final MP3 into the configured output directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from ..config.schema import OutputConfig
from .errors import OutputExistsError


def _candidate_with_suffix(target: Path) -> Path:
    stem, suffix = target.stem, target.suffix
    counter = 1
    while True:
        candidate = target.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def place_output(source: Path, target_filename: str, *, config: OutputConfig) -> Path:
    """Move `source` into `config.directory/target_filename` respecting `on_existing`."""
    out_dir = Path(config.directory).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / target_filename

    if target.exists():
        if config.on_existing == "error":
            raise OutputExistsError(
                f"refusing to overwrite existing file: {target}. "
                "Set output.on_existing=suffix to auto-rename, or remove the file."
            )
        target = _candidate_with_suffix(target)

    if source.resolve() != target.resolve():
        shutil.copy2(source, target)
    return target

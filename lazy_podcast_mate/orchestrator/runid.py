"""Generate a stable run_id from timestamp + article slug."""

from __future__ import annotations

from datetime import datetime, timezone

from ..output.filename import slugify


def make_run_id(title: str, *, now: datetime | None = None) -> str:
    when = now or datetime.now(timezone.utc)
    return f"{when.strftime('%Y%m%d-%H%M%S')}-{slugify(title, max_length=40) or 'untitled'}"

"""Render the versioned system prompt for the active `prompt_version`."""

from __future__ import annotations

from importlib.resources import files
from typing import Final

from .base import ArticleMetadata
from .errors import PermanentError

_PROMPT_PACKAGE: Final = "lazy_podcast_mate.script.prompts"


def load_prompt_template(version: str) -> str:
    try:
        resource = files(_PROMPT_PACKAGE).joinpath(f"{version}.md")
        return resource.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PermanentError(f"prompt version not found: {version}") from exc


def render_system_prompt(version: str, metadata: ArticleMetadata) -> str:
    template = load_prompt_template(version)
    return template.format(
        title=metadata.title,
        source_format=metadata.source_format,
    )


def build_user_message(cleaned_text: str) -> str:
    return f"---\n{cleaned_text}"

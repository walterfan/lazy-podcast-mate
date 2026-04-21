"""Output errors."""

from __future__ import annotations


class OutputError(Exception):
    """Raised when writing the final artefacts fails."""


class OutputExistsError(OutputError):
    """Target file exists and policy is `error`."""

"""Configuration errors."""

from __future__ import annotations


class ConfigError(Exception):
    """Raised when environment or YAML configuration is invalid.

    Carries a list of human-readable problems so the CLI can report
    every missing/invalid key at once instead of one-at-a-time.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(problems) if problems else "invalid configuration")

    def __str__(self) -> str:
        if not self.problems:
            return "invalid configuration"
        return "Configuration error:\n" + "\n".join(f"  - {p}" for p in self.problems)

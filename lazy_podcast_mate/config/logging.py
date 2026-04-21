"""Logging setup with secret redaction and JSON-lines support."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class SecretRedactor(logging.Filter):
    """Mask every occurrence of known secret values in log messages."""

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = tuple(s for s in secrets if s)

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._secrets:
            return True
        try:
            message = record.getMessage()
        except Exception:
            return True
        redacted = message
        for secret in self._secrets:
            if secret and secret in redacted:
                redacted = redacted.replace(secret, "***")
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


class JsonLineFormatter(logging.Formatter):
    """Format records as single-line JSON objects for machine consumption."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key in payload or key.startswith("_"):
                continue
            if key in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
            }:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    *,
    level: str,
    secrets: Iterable[str] = (),
    run_log_path: Path | None = None,
) -> logging.Logger:
    """Configure the root logger with stderr + optional JSON run log.

    Returns the root logger for convenience. Safe to call more than once;
    previous handlers are cleared to avoid duplicate output.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)

    root.setLevel(level.upper())
    redactor = SecretRedactor(secrets)

    human = logging.StreamHandler(sys.stderr)
    human.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    human.addFilter(redactor)
    root.addHandler(human)

    if run_log_path is not None:
        run_log_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl = logging.FileHandler(run_log_path, encoding="utf-8")
        jsonl.setFormatter(JsonLineFormatter())
        jsonl.addFilter(redactor)
        root.addHandler(jsonl)

    return root

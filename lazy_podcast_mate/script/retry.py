"""Tiny retry helper with exponential backoff for transient LLM/TTS failures."""

from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from ..config.schema import RetryConfig
from .errors import PermanentError, TransientError

_T = TypeVar("_T")

log = logging.getLogger(__name__)


def retry_call(
    fn: Callable[[], _T],
    *,
    config: RetryConfig,
    label: str,
    sleep: Callable[[float], None] = time.sleep,
    jitter: Callable[[], float] = random.random,
) -> _T:
    """Run `fn` with exponential backoff; re-raise the final `TransientError`
    on exhaustion, and let any `PermanentError` propagate immediately.
    """
    attempt = 0
    delay = config.initial_delay_seconds
    while True:
        attempt += 1
        try:
            return fn()
        except PermanentError:
            raise
        except TransientError as exc:
            if attempt >= config.max_attempts:
                log.warning(
                    "%s: exhausted retry budget after %d attempts: %s",
                    label,
                    attempt,
                    exc,
                )
                raise
            wait = min(delay, config.max_delay_seconds) * (0.5 + jitter())
            log.info(
                "%s: attempt %d failed (%s), retrying in %.2fs",
                label,
                attempt,
                exc,
                wait,
            )
            sleep(wait)
            delay = min(delay * config.backoff_factor, config.max_delay_seconds)

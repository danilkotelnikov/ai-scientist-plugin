"""Decorators for the orchestrator: retry + token tracking + phase logging.
Per spec §4.1.

Implementation note: vendored Sakana already brings `backoff`. We do NOT
import it here to keep the orchestrator standalone — we re-implement a tiny
exponential-backoff retry instead. ~30 LOC.
"""
from __future__ import annotations
import functools
import logging
import time
from typing import Callable, Iterable, Type

logger = logging.getLogger(__name__)


def retry_with_backoff(
    *,
    max_tries: int = 5,
    max_time: float = 300.0,
    on: Iterable[Type[BaseException]] = (Exception,),
    initial_delay: float = 1.0,
    factor: float = 2.0,
):
    """Exponential backoff. Retries only on listed exception types."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            start = time.monotonic()
            last_exc = None
            for attempt in range(1, max_tries + 1):
                if time.monotonic() - start >= max_time:
                    break
                try:
                    return fn(*args, **kwargs)
                except tuple(on) as exc:
                    last_exc = exc
                    if attempt == max_tries:
                        break
                    logger.warning(
                        "retry_with_backoff: %s attempt %d/%d failed (%s); sleeping %.1fs",
                        fn.__name__, attempt, max_tries, exc, delay,
                    )
                    time.sleep(delay)
                    delay *= factor
            if last_exc is None:
                # max_time was exhausted before the first attempt completed.
                raise TimeoutError(
                    f"retry_with_backoff: {fn.__name__} exceeded max_time={max_time}s "
                    f"before any attempt completed"
                )
            raise last_exc
        return wrapper
    return decorator


def track_tokens(*, phase: str, agent: str):
    """Wrap a function whose return value contains 'prompt_tokens' /
    'completion_tokens' / optional 'thinking_tokens'. The tracker is a global
    singleton (see tokens.py).
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            from .tokens import _GLOBAL_TRACKER
            result = fn(*args, **kwargs)
            if isinstance(result, dict):
                _GLOBAL_TRACKER.add(
                    phase=phase,
                    agent=agent,
                    prompt_tok=int(result.get("prompt_tokens", 0) or 0),
                    completion_tok=int(result.get("completion_tokens", 0) or 0),
                    thinking_tok=int(result.get("thinking_tokens", 0) or 0),
                )
            return result
        return wrapper
    return decorator


def log_phase(fn: Callable) -> Callable:
    """Log start/end of a phase function."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        logger.info("start: %s", fn.__name__)
        start = time.monotonic()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed = time.monotonic() - start
            logger.info("end: %s (%.2fs)", fn.__name__, elapsed)
    return wrapper

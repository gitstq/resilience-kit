"""Retry policies with configurable backoff and jitter."""

from __future__ import annotations

import functools
import random
import threading
import time
from typing import Any, Callable, Iterable, Optional, Tuple, Type, Union


def exponential_backoff(
    initial: float = 0.1,
    multiplier: float = 2.0,
    maximum: float = 30.0,
) -> Callable[[int], float]:
    """Return a delay function computing ``initial * multiplier ** attempt``.

    The result is capped at ``maximum``.
    """
    if initial <= 0:
        raise ValueError("initial must be greater than 0")
    if multiplier < 1:
        raise ValueError("multiplier must be at least 1")
    if maximum < initial:
        raise ValueError("maximum must be at least initial")

    def delay(attempt: int) -> float:
        return min(maximum, initial * (multiplier ** max(0, attempt - 1)))

    return delay


def constant_backoff(delay: float = 0.1) -> Callable[[int], float]:
    """Return a delay function that always yields ``delay``."""
    if delay < 0:
        raise ValueError("delay must be >= 0")
    return lambda _attempt: delay


def with_jitter(
    delay_fn: Callable[[int], float],
    jitter: str = "full",
    *,
    rng: Optional[random.Random] = None,
) -> Callable[[int], float]:
    """Wrap a delay function with jitter to avoid thundering herds.

    Args:
        jitter: One of ``"none"``, ``"full"`` or ``"equal"``.
            ``full`` -> uniform(0, delay); ``equal`` -> delay/2 + uniform(0, delay/2).
        rng: Injectable RNG for deterministic tests.
    """
    if jitter not in ("none", "full", "equal"):
        raise ValueError("jitter must be 'none', 'full' or 'equal'")
    generator = rng or random

    def delay(attempt: int) -> float:
        base = max(0.0, delay_fn(attempt))
        if jitter == "none":
            return base
        if jitter == "full":
            return generator.uniform(0.0, base)
        return base / 2 + generator.uniform(0.0, base / 2)

    return delay


RetryException = Union[Type[BaseException], Tuple[Type[BaseException], ...]]


class Retry:
    """Retry decorator with pluggable backoff and exception filtering.

    Args:
        attempts: Total number of attempts, including the first one.
        backoff: A callable ``attempt -> seconds``; ``attempt`` is 1-based.
            Defaults to exponential backoff with full jitter.
        exceptions: Exception types that trigger a retry.
        on_retry: Optional callback invoked before each retry as
            ``(exception, attempt, delay)``.

    Example:
        >>> state = {"n": 0}
        >>> @Retry(attempts=3, backoff=lambda _: 0)
        ... def flaky():
        ...     state["n"] += 1
        ...     if state["n"] < 3:
        ...         raise ValueError("not yet")
        ...     return "ok"
        >>> flaky()
        'ok'
        >>> state["n"]
        3
    """

    def __init__(
        self,
        attempts: int = 3,
        backoff: Optional[Callable[[int], float]] = None,
        exceptions: RetryException = Exception,
        on_retry: Optional[Callable[[BaseException, int, float], None]] = None,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        attempts = int(attempts)
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        self.attempts = attempts
        self.backoff = exponential_backoff() if backoff is None else backoff
        self.exceptions = exceptions
        self.on_retry = on_retry
        self._sleep = sleep
        self._lock = threading.Lock()
        self.counters = {"attempts": 0, "retries": 0, "succeeded": 0, "exhausted": 0}

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``func`` with retries."""
        last_exc: Optional[BaseException] = None
        for attempt in range(1, self.attempts + 1):
            with self._lock:
                self.counters["attempts"] += 1
            try:
                result = func(*args, **kwargs)
            except self.exceptions as exc:
                last_exc = exc
                if attempt == self.attempts:
                    with self._lock:
                        self.counters["exhausted"] += 1
                    raise
                delay = max(0.0, float(self.backoff(attempt)))
                with self._lock:
                    self.counters["retries"] += 1
                if self.on_retry is not None:
                    self.on_retry(exc, attempt, delay)
                if delay:
                    self._sleep(delay)
            else:
                with self._lock:
                    self.counters["succeeded"] += 1
                return result
        # Unreachable, but keeps type checkers happy.
        assert last_exc is not None
        raise last_exc

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)

        return wrapper


def retry(
    attempts: int = 3,
    backoff: Optional[Callable[[int], float]] = None,
    exceptions: RetryException = Exception,
    on_retry: Optional[Callable[[BaseException, int, float], None]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Functional decorator alias for :class:`Retry`.

    Also supports the bare ``@retry`` form.
    """
    if callable(attempts) and not isinstance(attempts, int):  # bare @retry
        func = attempts
        return Retry().call(func)  # type: ignore[arg-type]

    policy = Retry(attempts, backoff, exceptions, on_retry)
    return policy

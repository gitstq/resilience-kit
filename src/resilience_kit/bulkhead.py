"""Bulkhead (concurrency limiter) implementation."""

from __future__ import annotations

import functools
import threading
import time
from typing import Any, Callable, Optional


class BulkheadFull(Exception):
    """Raised when no concurrency slot is available in non-blocking mode."""


class Bulkhead:
    """Limit the number of concurrent executions of a callable.

    Implemented as a counting semaphore with optional acquisition timeout.

    Args:
        limit: Maximum number of concurrent holders (must be >= 1).
        max_wait: Seconds an acquire will wait before raising
            :class:`BulkheadFull``. ``None`` waits forever; ``0`` fails fast.

    Example:
        >>> bh = Bulkhead(limit=2, max_wait=0)
        >>> @bh
        ... def work():
        ...     return 1
        >>> work()
        1
    """

    def __init__(self, limit: int, max_wait: Optional[float] = None) -> None:
        limit = int(limit)
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if max_wait is not None and max_wait < 0:
            raise ValueError("max_wait must be >= 0 or None")
        self.limit = limit
        self.max_wait = max_wait
        self._sem = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self.counters = {"accepted": 0, "rejected": 0, "in_flight": 0}

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire a slot, returning ``True`` on success."""
        wait = self.max_wait if timeout is None else timeout
        if wait is None:
            acquired = self._sem.acquire()
        elif wait == 0:
            acquired = self._sem.acquire(blocking=False)
        else:
            acquired = self._sem.acquire(timeout=wait)
        if acquired:
            with self._lock:
                self.counters["accepted"] += 1
                self.counters["in_flight"] += 1
        else:
            with self._lock:
                self.counters["rejected"] += 1
        return acquired

    def release(self) -> None:
        """Release a previously acquired slot."""
        with self._lock:
            self.counters["in_flight"] -= 1
        self._sem.release()

    def try_acquire(self) -> bool:
        """Non-blocking acquisition attempt."""
        return self.acquire(timeout=0)

    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Run ``func`` inside a bulkhead slot.

        Raises:
            BulkheadFull: If no slot can be acquired.
        """
        if not self.acquire():
            raise BulkheadFull("bulkhead is full")
        try:
            return func(*args, **kwargs)
        finally:
            self.release()

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)

        return wrapper

    @property
    def in_flight(self) -> int:
        with self._lock:
            return self.counters["in_flight"]

    def __repr__(self) -> str:
        return f"Bulkhead(limit={self.limit}, in_flight={self.in_flight}, max_wait={self.max_wait})"

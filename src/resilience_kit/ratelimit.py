"""Rate-limiting primitives.

Two algorithms are provided:

* :class:`TokenBucket` -- allows controlled bursts, smooth long-term rate.
* :class:`SlidingWindow` -- hard upper bound in any rolling time window.

Both are thread-safe and use a monotonic clock, so wall-clock adjustments
cannot corrupt their accounting.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable, Deque, Optional


class RateLimitExceeded(Exception):
    """Raised by :meth:`acquire` when no permit is available.

    ``retry_after`` is the number of seconds the caller should wait before
    trying again (always ``>= 0``).
    """

    def __init__(self, message: str = "rate limit exceeded", retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = max(0.0, float(retry_after))


class TokenBucket:
    """A token-bucket rate limiter.

    Tokens are added continuously at ``rate`` tokens/second, up to
    ``capacity``. Every operation consumes one or more tokens. The bucket
    therefore permits bursts of at most ``capacity`` while enforcing the
    average rate.

    Args:
        rate: Sustained refill rate, in tokens per second (must be > 0).
        capacity: Maximum burst size. Defaults to ``rate`` (one second burst).
        clock: Injectable monotonic clock, primarily for deterministic tests.

    Example:
        >>> limiter = TokenBucket(rate=5, capacity=5, clock=lambda: 0.0)
        >>> [limiter.try_acquire() for _ in range(6)]
        [True, True, True, True, True, False]
    """

    def __init__(
        self,
        rate: float,
        capacity: Optional[float] = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        rate = float(rate)
        if rate <= 0:
            raise ValueError("rate must be greater than 0")
        capacity = float(rate) if capacity is None else float(capacity)
        if capacity <= 0:
            raise ValueError("capacity must be greater than 0")
        self.rate = rate
        self.capacity = capacity
        self._clock = clock
        self._tokens = capacity
        self._updated = clock()
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        elapsed = now - self._updated
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._updated = now
        elif elapsed < 0:
            # A misbehaving injected clock must never move us backwards.
            self._updated = now

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Consume ``tokens`` if available; return ``True`` on success.

        This method never blocks.
        """
        if tokens <= 0:
            raise ValueError("tokens must be greater than 0")
        with self._lock:
            self._refill(self._clock())
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def acquire(self, tokens: float = 1.0, *, timeout: Optional[float] = None) -> None:
        """Block until ``tokens`` can be consumed.

        Args:
            tokens: Number of tokens to consume.
            timeout: Maximum seconds to wait. ``None`` waits forever.

        Raises:
            RateLimitExceeded: If the budget cannot be obtained in time.
        """
        if tokens > self.capacity:
            raise RateLimitExceeded("requested tokens exceed bucket capacity")
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while True:
            with self._lock:
                now = self._clock()
                self._refill(now)
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                wait = (tokens - self._tokens) / self.rate
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RateLimitExceeded(retry_after=wait)
                wait = min(wait, remaining)
            time.sleep(min(wait, 0.05))  # wake periodically to honour timeout

    @property
    def available(self) -> float:
        """Current number of available tokens (refills on read)."""
        with self._lock:
            self._refill(self._clock())
            return self._tokens

    def __repr__(self) -> str:
        return f"TokenBucket(rate={self.rate}, capacity={self.capacity}, available={self.available:.2f})"


class SlidingWindow:
    """A sliding-window (rolling log) rate limiter.

    Tracks the timestamps of recent acquisitions and rejects a new request
    when more than ``limit`` events fall inside the last ``window`` seconds.
    Unlike a fixed window, it cannot be gamed by straddling a boundary.

    Args:
        limit: Maximum number of acquisitions per window (must be >= 1).
        window: Window length in seconds (must be > 0).
        clock: Injectable monotonic clock, primarily for deterministic tests.
    """

    def __init__(
        self,
        limit: int,
        window: float,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        limit = int(limit)
        window = float(window)
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window <= 0:
            raise ValueError("window must be greater than 0")
        self.limit = limit
        self.window = window
        self._clock = clock
        self._events: Deque[float] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def _retry_after(self, now: float) -> float:
        if not self._events:
            return 0.0
        return max(0.0, self._events[0] + self.window - now)

    def try_acquire(self) -> bool:
        """Record an acquisition if it fits into the current window."""
        with self._lock:
            now = self._clock()
            self._prune(now)
            if len(self._events) < self.limit:
                self._events.append(now)
                return True
            return False

    def acquire(self, *, timeout: Optional[float] = None) -> None:
        """Block until a slot is free.

        Raises:
            RateLimitExceeded: If no slot frees up before ``timeout``.
        """
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        while True:
            with self._lock:
                now = self._clock()
                self._prune(now)
                if len(self._events) < self.limit:
                    self._events.append(now)
                    return
                wait = self._retry_after(now)
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RateLimitExceeded(retry_after=wait)
                wait = min(wait, remaining)
            time.sleep(min(max(wait, 0.0), 0.05))

    @property
    def remaining(self) -> int:
        """Free slots in the current window."""
        with self._lock:
            self._prune(self._clock())
            return self.limit - len(self._events)

    def __repr__(self) -> str:
        return f"SlidingWindow(limit={self.limit}, window={self.window}, remaining={self.remaining})"

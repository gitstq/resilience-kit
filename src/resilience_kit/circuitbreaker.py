"""Circuit breaker implementation.

States::

    CLOSED --(failures >= threshold)--> OPEN --(timeout)--> HALF_OPEN
       ^                                  |                    |
       +----------(probe ok)--------------+--------------------+
       |                                                       |
       +------------------(probe fails)------------------------+

While OPEN, calls fail fast without touching the protected resource. After
``reset_timeout`` seconds a single probe is allowed through (HALF_OPEN). If
it succeeds the breaker returns to CLOSED; otherwise it re-opens.
"""

from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable, Iterable, Optional, Tuple, Type, Union


class CircuitState(str, Enum):
    """Possible states of a :class:`CircuitBreaker`."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, retry_after: float = 0.0, message: str = "circuit breaker is open") -> None:
        super().__init__(message)
        self.retry_after = max(0.0, float(retry_after))


class CircuitBreaker:
    """A thread-safe circuit breaker.

    Args:
        failure_threshold: Consecutive failures needed to open the circuit.
        reset_timeout: Seconds to stay OPEN before allowing a probe.
        expected_exceptions: Exception types counted as failures. Other
            exceptions propagate immediately and do not change the state.
        half_open_max_calls: Number of successful probes needed to close.
        clock: Injectable monotonic clock, primarily for deterministic tests.

    Example:
        >>> breaker = CircuitBreaker(failure_threshold=2, reset_timeout=1)
        >>> @breaker
        ... def fragile(flag):
        ...     if not flag:
        ...         raise ValueError("boom")
        ...     return "ok"
        >>> fragile(True)
        'ok'
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        expected_exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = Exception,
        half_open_max_calls: int = 1,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        failure_threshold = int(failure_threshold)
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if reset_timeout <= 0:
            raise ValueError("reset_timeout must be greater than 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")

        self.failure_threshold = failure_threshold
        self.reset_timeout = float(reset_timeout)
        self.expected_exceptions = expected_exceptions
        self.half_open_max_calls = int(half_open_max_calls)
        self._clock = clock

        self._state = CircuitState.CLOSED
        self._failures = 0
        self._successes = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()
        self._probe_lock = threading.Lock()
        self._listeners: list[Callable[[CircuitState, CircuitState], None]] = []

        # Counters useful for telemetry / dashboards.
        self.counters = {
            "calls": 0,
            "successful": 0,
            "failed": 0,
            "rejected": 0,
            "state_changes": 0,
        }

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------
    def _transition(self, new_state: CircuitState, now: float) -> None:
        if new_state == self._state:
            return
        old = self._state
        self._state = new_state
        self._opened_at = now if new_state is CircuitState.OPEN else 0.0
        self.counters["state_changes"] += 1
        for listener in tuple(self._listeners):
            listener(old, new_state)

    def add_listener(self, listener: Callable[[CircuitState, CircuitState], None]) -> None:
        """Register a callback invoked on every state transition."""
        if not callable(listener):
            raise TypeError("listener must be callable")
        with self._lock:
            self._listeners.append(listener)

    @property
    def state(self) -> CircuitState:
        """Current state, materialising a HALF_OPEN transition if due."""
        with self._lock:
            if self._state is CircuitState.OPEN and self._clock() - self._opened_at >= self.reset_timeout:
                self._transition(CircuitState.HALF_OPEN, self._clock())
                self._successes = 0
            return self._state

    @property
    def failures(self) -> int:
        with self._lock:
            return self._failures

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        with self._lock:
            self._failures = 0
            self._successes = 0
            self._transition(CircuitState.CLOSED, self._clock())

    def retry_after(self) -> float:
        """Seconds until the circuit may be probed again (0 when not OPEN)."""
        with self._lock:
            if self._state is not CircuitState.OPEN:
                return 0.0
            return max(0.0, self._opened_at + self.reset_timeout - self._clock())

    # ------------------------------------------------------------------
    # Recording outcomes
    # ------------------------------------------------------------------
    def _record_success(self) -> None:
        with self._lock:
            now = self._clock()
            self.counters["successful"] += 1
            if self._state is CircuitState.HALF_OPEN:
                self._successes += 1
                if self._successes >= self.half_open_max_calls:
                    self._failures = 0
                    self._transition(CircuitState.CLOSED, now)
            else:
                self._failures = 0

    def _record_failure(self) -> None:
        with self._lock:
            now = self._clock()
            self.counters["failed"] += 1
            self._failures += 1
            if self._state is CircuitState.HALF_OPEN or self._failures >= self.failure_threshold:
                self._transition(CircuitState.OPEN, now)

    # ------------------------------------------------------------------
    # Invocation
    # ------------------------------------------------------------------
    def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke ``func`` under the breaker's protection.

        Raises:
            CircuitOpenError: If the circuit is currently OPEN.
        """
        now = self._clock()
        with self._lock:
            if self._state is CircuitState.OPEN:
                if now - self._opened_at >= self.reset_timeout:
                    self._transition(CircuitState.HALF_OPEN, now)
                    self._successes = 0
                else:
                    self.counters["rejected"] += 1
                    raise CircuitOpenError(retry_after=self._opened_at + self.reset_timeout - now)
            state = self._state
            self.counters["calls"] += 1

        # Only one probe at a time in HALF_OPEN; CLOSED calls run concurrently.
        probe_token = None
        if state is CircuitState.HALF_OPEN:
            probe_token = self._probe_lock.acquire(blocking=False)
            if not probe_token:
                with self._lock:
                    self.counters["rejected"] += 1
                raise CircuitOpenError(retry_after=self.retry_after(), message="a probe is already in flight")

        try:
            result = func(*args, **kwargs)
        except self.expected_exceptions:
            self._record_failure()
            raise
        except BaseException:
            # Unexpected errors (e.g. KeyboardInterrupt) are not our concern.
            with self._lock:
                self.counters["calls"] -= 1
            raise
        else:
            self._record_success()
            return result
        finally:
            if probe_token:
                self._probe_lock.release()

    def __call__(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Use the breaker as a decorator."""

        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return self.call(func, *args, **kwargs)

        wrapper.__name__ = getattr(func, "__name__", "wrapped")
        wrapper.__doc__ = getattr(func, "__doc__", None)
        wrapper.__wrapped__ = func
        return wrapper

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.value}, failures={self._failures}, "
            f"threshold={self.failure_threshold})"
        )


def resilient(
    failure_threshold: int = 5,
    reset_timeout: float = 30.0,
    expected_exceptions: Union[Type[BaseException], Tuple[Type[BaseException], ...]] = Exception,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator shorthand for creating and applying a :class:`CircuitBreaker`."""

    breaker = CircuitBreaker(failure_threshold, reset_timeout, expected_exceptions)

    def decorate(func: Callable[..., Any]) -> Callable[..., Any]:
        return breaker(func)

    return decorate

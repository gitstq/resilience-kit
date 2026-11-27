"""resilience-kit -- zero-dependency resilience primitives for Python.

Modules:
    ratelimit: Token bucket and sliding window rate limiters.
    circuitbreaker: Circuit breaker with state-change listeners.
    retry: Retries with exponential backoff and jitter.
    bulkhead: Concurrency limiting.
"""

from .bulkhead import Bulkhead, BulkheadFull
from .circuitbreaker import CircuitBreaker, CircuitOpenError, CircuitState, resilient
from .ratelimit import RateLimitExceeded, SlidingWindow, TokenBucket
from .retry import Retry, constant_backoff, exponential_backoff, retry, with_jitter

__version__ = "1.0.0"
__all__ = [
    "Bulkhead",
    "BulkheadFull",
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "RateLimitExceeded",
    "Retry",
    "SlidingWindow",
    "TokenBucket",
    "constant_backoff",
    "exponential_backoff",
    "resilient",
    "retry",
    "with_jitter",
]

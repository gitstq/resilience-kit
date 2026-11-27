"""Quick-start example: composing several resilience primitives.

Run with::

    PYTHONPATH=src python3 examples/quickstart.py
"""

import random
import time

from resilience_kit import (
    Bulkhead,
    CircuitBreaker,
    CircuitOpenError,
    RateLimitExceeded,
    Retry,
    TokenBucket,
    exponential_backoff,
    with_jitter,
)

# 1. Rate limiting -- allow 10 bursts, refilling 2 tokens per second.
bucket = TokenBucket(rate=2, capacity=10)

# 2. Circuit breaker -- open after 3 consecutive failures for 2 seconds.
breaker = CircuitBreaker(failure_threshold=3, reset_timeout=2)
breaker.add_listener(lambda old, new: print(f"[breaker] {old.value} -> {new.value}"))

# 3. Retry -- 3 attempts with exponential backoff and full jitter.
retry = Retry(attempts=3, backoff=with_jitter(exponential_backoff(initial=0.01)))

# 4. Bulkhead -- at most 4 concurrent calls.
bulkhead = Bulkhead(limit=4, max_wait=1)


def unreliable_remote_call(value: int) -> int:
    """Pretend to call a flaky remote service (20% failure rate)."""
    if random.random() < 0.2:
        raise ConnectionError("simulated remote failure")
    return value * 2


def resilient_call(value: int):
    if not bucket.try_acquire():
        raise RateLimitExceeded(retry_after=0.5)
    return bulkhead.call(lambda: retry.call(lambda: breaker.call(unreliable_remote_call, value)))


if __name__ == "__main__":
    random.seed(7)
    for i in range(12):
        try:
            result = resilient_call(i)
            print(f"call {i:2d} -> {result}")
        except (CircuitOpenError, RateLimitExceeded, ConnectionError) as exc:
            print(f"call {i:2d} -> rejected: {type(exc).__name__}: {exc}")
        time.sleep(0.05)
    print("\ncounters:", breaker.counters, retry.counters, bulkhead.counters)

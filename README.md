<div align="center">

# resilience-kit

**Zero-dependency resilience primitives for Python.**

[English](README.md) · [简体中文](README.zh-CN.md) · [繁體中文](README.zh-TW.md)

[![PyPI](https://img.shields.io/badge/PyPI-1.0.0-blue.svg)](https://pypi.org/project/resilience-kit/)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-49%20passed-brightgreen.svg)](tests/)

</div>

## 🎉 Introduction

When a service degrades, a single slow or failing dependency can cascade into a total outage. **resilience-kit** gives your Python applications the small, composable building blocks they need to survive that reality — without pulling in a single third-party dependency.

It is a clean-room implementation inspired by the *product ideas* behind established rate-limiting and fault-tolerance tools (such as token-bucket limiters and circuit breakers). No source code was copied; the architecture, API and tests were written from scratch with a focus on clarity, thread safety and deterministic testability.

Design goals:

- **Zero dependencies** — standard library only. Works in constrained environments, air-gapped servers and minimal containers.
- **Composable** — every primitive is usable alone or stacked into a single resilience pipeline.
- **Thread-safe** — all mutable state guarded by locks; clocks are injectable for deterministic tests.
- **Typed & documented** — ships with `py.typed` and docstrings on every public symbol.

## ✨ Features

| Primitive | Module | What it solves |
|-----------|--------|----------------|
| 🚦 `TokenBucket` | `ratelimit` | Smooth long-term rate with controlled bursts |
| 🪟 `SlidingWindow` | `ratelimit` | Strict cap in any rolling time window |
| ⚡ `CircuitBreaker` | `circuitbreaker` | Fail fast when a dependency is down; auto-probe recovery |
| 🔁 `Retry` / `retry` | `retry` | Retries with exponential/constant backoff and jitter |
| 🧱 `Bulkhead` | `bulkhead` | Bound concurrency to protect thread/resource pools |

Highlights:

- 🔒 Thread-safe token bucket and sliding-window limiters using a monotonic clock.
- 🔌 Circuit breaker with `CLOSED → OPEN → HALF_OPEN → CLOSED` state machine and change listeners.
- 🎲 Backoff with `full` / `equal` / `none` jitter to avoid thundering herds.
- 🧵 Semaphore-based bulkhead with non-blocking and timed acquisition.
- 🧪 49 unit tests covering concurrency, timing, edge cases and state transitions.

## 🚀 Quick start

Install from source (PyPI package coming soon):

```bash
git clone https://github.com/gitstq/resilience-kit.git
cd resilience-kit
python3 -m pip install .
```

Verify the installation:

```python
from resilience_kit import TokenBucket, CircuitBreaker, Retry, Bulkhead

limiter = TokenBucket(rate=5, capacity=5)
print(limiter.try_acquire())  # True
```

Run the bundled full-featured example:

```bash
PYTHONPATH=src python3 examples/quickstart.py
```

## 📖 Usage guide

### 🚦 Token bucket

```python
from resilience_kit import TokenBucket, RateLimitExceeded

bucket = TokenBucket(rate=2, capacity=4)

if bucket.try_acquire():
    handle_request()          # non-blocking
else:
    raise RateLimitExceeded()

bucket.acquire(timeout=1.0)   # blocking variant, waits up to 1s
```

### 🪟 Sliding window

```python
from resilience_kit import SlidingWindow

window = SlidingWindow(limit=100, window=60)  # 100 req / 60s
if window.try_acquire():
    handle_request()
```

### ⚡ Circuit breaker

```python
from resilience_kit import CircuitBreaker, CircuitOpenError

breaker = CircuitBreaker(failure_threshold=3, reset_timeout=30)
breaker.add_listener(lambda old, new: print(f"{old.value} -> {new.value}"))

@breaker
def call_remote():
    return remote_api()

try:
    call_remote()
except CircuitOpenError as exc:
    print(f"retry after {exc.retry_after:.1f}s")
```

### 🔁 Retry with backoff

```python
from resilience_kit import Retry, exponential_backoff, with_jitter

policy = Retry(
    attempts=4,
    backoff=with_jitter(exponential_backoff(initial=0.1, maximum=5)),
    exceptions=(ConnectionError, TimeoutError),
)

result = policy.call(call_remote)
```

Or as a decorator:

```python
@Retry(attempts=3, backoff=lambda _: 0)
def flaky():
    ...
```

### 🧱 Bulkhead

```python
from resilience_kit import Bulkhead, BulkheadFull

pool = Bulkhead(limit=10, max_wait=0.5)

@pool
def heavy_task():
    ...
```

### 🧩 Composing a full pipeline

```python
from resilience_kit import (
    TokenBucket, CircuitBreaker, Retry, Bulkhead,
    exponential_backoff, with_jitter,
)

bucket  = TokenBucket(rate=50, capacity=50)
breaker = CircuitBreaker(failure_threshold=5, reset_timeout=10)
retry   = Retry(attempts=3, backoff=with_jitter(exponential_backoff()))
pool    = Bulkhead(limit=20)

def guarded(*args, **kwargs):
    bucket.acquire(timeout=1)
    return pool.call(lambda: retry.call(lambda: breaker.call(call_remote, *args, **kwargs)))
```

See [`examples/quickstart.py`](examples/quickstart.py) for a runnable version.

## 💡 Design & iteration

This project follows a deliberate "reference the idea, not the code" approach:

| Iteration | Change | Rationale |
|-----------|--------|-----------|
| v1.0.0 | Initial four primitives | Cover the most common resilience patterns with zero dependencies |
| Deterministic clocks | Injectable `clock=` parameter | Removes flaky timing tests; enables exact boundary assertions |
| Jitter strategies | `full` / `equal` / `none` | Prevents synchronized retries (thundering herd) in distributed clients |
| Half-open probe lock | Single in-flight probe | Avoids a stampede of probes overwhelming a recovering dependency |
| Telemetry counters | `.counters` dict per primitive | Cheap observability hooks without a metrics dependency |
| Thread-safety audit | Locks around all mutable state | Guarantees correctness under concurrent request handling |

Deliberate non-goals: no distributed coordination (use Redis/etcd when you need cross-process limits), no async-specific variants in v1.0.0 (the primitives are blocking and safe to call from worker threads).

## 📦 Build & deployment

```bash
# Run the test suite
PYTHONPATH=src python3 -m unittest discover -s tests -v

# Build sdist + wheel
./build.sh
```

Artifacts land in `dist/`:

```
resilience_kit-1.0.0-py3-none-any.whl
resilience_kit-1.0.0.tar.gz
```

Verify integrity:

```bash
cd dist && sha256sum *
```

As a **library**, this project intentionally publishes no binary Release. Integrate it by adding the wheel/sdist to your dependency lockfile or installing directly:

```bash
python3 -m pip install ./dist/resilience_kit-1.0.0-py3-none-any.whl
```

## 🤝 Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

- 🐛 Report bugs with a minimal reproducer.
- ✨ Propose new primitives with a clear use case and tests.
- ✅ Keep the suite green: all tests must pass, and new behaviour needs new tests.
- 📝 Follow conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`).

## 📄 License

Released under the [MIT License](LICENSE). Use it freely in personal and commercial projects.

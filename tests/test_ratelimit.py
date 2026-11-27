"""Tests for resilience_kit.ratelimit."""

import threading
import time
import unittest

from resilience_kit.ratelimit import RateLimitExceeded, SlidingWindow, TokenBucket


class FakeClock:
    """Deterministic monotonic clock."""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TestTokenBucket(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ValueError):
            TokenBucket(0)
        with self.assertRaises(ValueError):
            TokenBucket(1, capacity=0)

    def test_burst_then_refill(self):
        clock = FakeClock()
        bucket = TokenBucket(rate=2, capacity=4, clock=clock)
        self.assertTrue(all(bucket.try_acquire() for _ in range(4)))
        self.assertFalse(bucket.try_acquire())
        self.assertEqual(bucket.available, 0)
        clock.advance(1.0)
        self.assertAlmostEqual(bucket.available, 2.0)
        self.assertTrue(bucket.try_acquire())
        self.assertAlmostEqual(bucket.available, 1.0)

    def test_capacity_cap(self):
        clock = FakeClock()
        bucket = TokenBucket(rate=1, capacity=2, clock=clock)
        clock.advance(1000)
        self.assertEqual(bucket.available, 2)

    def test_multi_token_acquire(self):
        bucket = TokenBucket(rate=1, capacity=3, clock=FakeClock())
        self.assertTrue(bucket.try_acquire(3))
        self.assertFalse(bucket.try_acquire(1))

    def test_request_over_capacity(self):
        bucket = TokenBucket(rate=1, capacity=1, clock=FakeClock())
        with self.assertRaises(RateLimitExceeded):
            bucket.acquire(2)

    def test_acquire_blocks_until_refill(self):
        clock = FakeClock()
        bucket = TokenBucket(rate=10, capacity=1, clock=clock)
        self.assertTrue(bucket.try_acquire())

        original_sleep = time.sleep
        sleeps = []
        calls = {"n": 0}

        def fake_sleep(seconds):
            sleeps.append(seconds)
            calls["n"] += 1
            if calls["n"] == 1:
                clock.advance(0.2)

        time.sleep = fake_sleep
        try:
            bucket.acquire(timeout=1)
        finally:
            time.sleep = original_sleep
        self.assertTrue(sleeps)

    def test_acquire_timeout(self):
        bucket = TokenBucket(rate=0.001, capacity=1, clock=FakeClock())
        self.assertTrue(bucket.try_acquire())  # drain the bucket
        with self.assertRaises(RateLimitExceeded) as ctx:
            bucket.acquire(timeout=0.01)
        self.assertGreaterEqual(ctx.exception.retry_after, 0)

    def test_thread_safety(self):
        clock = time.monotonic
        bucket = TokenBucket(rate=1000, capacity=10000, clock=clock)
        acquired = []
        lock = threading.Lock()

        def worker():
            ok = bucket.try_acquire()
            with lock:
                acquired.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(acquired), 200)

    def test_negative_clock_does_not_rewind(self):
        clock = FakeClock(10)
        bucket = TokenBucket(rate=1, capacity=2, clock=clock)
        bucket.try_acquire()
        clock.now = 5
        self.assertEqual(bucket.available, 1)


class TestSlidingWindow(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ValueError):
            SlidingWindow(0, 1)
        with self.assertRaises(ValueError):
            SlidingWindow(1, 0)

    def test_limit(self):
        clock = FakeClock()
        window = SlidingWindow(limit=2, window=10, clock=clock)
        self.assertTrue(window.try_acquire())
        self.assertTrue(window.try_acquire())
        self.assertFalse(window.try_acquire())
        self.assertEqual(window.remaining, 0)

    def test_prune_after_window(self):
        clock = FakeClock()
        window = SlidingWindow(limit=2, window=1, clock=clock)
        window.try_acquire()
        window.try_acquire()
        self.assertFalse(window.try_acquire())
        clock.advance(1.01)
        self.assertTrue(window.try_acquire())
        self.assertEqual(window.remaining, 1)

    def test_acquire_timeout(self):
        window = SlidingWindow(limit=1, window=1, clock=FakeClock())
        window.try_acquire()
        with self.assertRaises(RateLimitExceeded):
            window.acquire(timeout=0.01)

    def test_thread_safety(self):
        window = SlidingWindow(limit=50, window=1000)
        results = []
        lock = threading.Lock()

        def worker():
            ok = window.try_acquire()
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(results), 50)


if __name__ == "__main__":
    unittest.main()

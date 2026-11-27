"""Tests for resilience_kit.circuitbreaker."""

import threading
import time
import unittest

from resilience_kit.circuitbreaker import CircuitBreaker, CircuitOpenError, CircuitState, resilient


class FakeClock:
    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def fail():
    raise ValueError("boom")


def succeed():
    return "ok"


class TestCircuitBreaker(unittest.TestCase):
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=2, clock=FakeClock())
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.call(succeed), "ok")

    def test_opens_after_threshold(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=2, reset_timeout=10, clock=clock)
        with self.assertRaises(ValueError):
            cb.call(fail)
        with self.assertRaises(ValueError):
            cb.call(fail)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_rejects_while_open(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=10, clock=clock)
        with self.assertRaises(ValueError):
            cb.call(fail)
        with self.assertRaises(CircuitOpenError) as ctx:
            cb.call(succeed)
        self.assertGreaterEqual(ctx.exception.retry_after, 0)
        self.assertEqual(cb.counters["rejected"], 1)

    def test_half_open_recovery(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=5, clock=clock)
        with self.assertRaises(ValueError):
            cb.call(fail)
        self.assertEqual(cb.state, CircuitState.OPEN)
        clock.advance(5)
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        self.assertEqual(cb.call(succeed), "ok")
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failures, 0)

    def test_half_open_failure_reopens(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=5, clock=clock)
        with self.assertRaises(ValueError):
            cb.call(fail)
        clock.advance(5)
        with self.assertRaises(ValueError):
            cb.call(fail)
        self.assertEqual(cb.state, CircuitState.OPEN)

    def test_unexpected_exception_not_counted(self):
        cb = CircuitBreaker(failure_threshold=1, expected_exceptions=ValueError, clock=FakeClock())

        def boom():
            raise TypeError("unexpected")

        with self.assertRaises(TypeError):
            cb.call(boom)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertEqual(cb.failures, 0)

    def test_listener(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=5, clock=clock)
        transitions = []
        cb.add_listener(lambda old, new: transitions.append((old, new)))
        with self.assertRaises(ValueError):
            cb.call(fail)
        clock.advance(5)
        cb.call(succeed)
        self.assertIn((CircuitState.CLOSED, CircuitState.OPEN), transitions)
        self.assertIn((CircuitState.OPEN, CircuitState.HALF_OPEN), transitions)
        self.assertIn((CircuitState.HALF_OPEN, CircuitState.CLOSED), transitions)

    def test_manual_reset(self):
        cb = CircuitBreaker(failure_threshold=1, clock=FakeClock())
        with self.assertRaises(ValueError):
            cb.call(fail)
        self.assertEqual(cb.state, CircuitState.OPEN)
        cb.reset()
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_decorator(self):
        cb = CircuitBreaker(failure_threshold=2, clock=FakeClock())

        @cb
        def flaky(flag):
            if flag:
                return "ok"
            raise ValueError("boom")

        self.assertEqual(flaky(True), "ok")
        with self.assertRaises(ValueError):
            flaky(False)
        with self.assertRaises(ValueError):
            flaky(False)
        with self.assertRaises(CircuitOpenError):
            flaky(True)

    def test_resilient_decorator(self):
        @resilient(failure_threshold=1, reset_timeout=10)
        def f():
            return 1

        self.assertEqual(f(), 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            CircuitBreaker(failure_threshold=0)
        with self.assertRaises(ValueError):
            CircuitBreaker(reset_timeout=0)

    def test_concurrent_calls(self):
        cb = CircuitBreaker(failure_threshold=500, reset_timeout=10)
        results = []
        lock = threading.Lock()

        def worker(i):
            try:
                cb.call(succeed)
                ok = True
            except Exception:
                ok = False
            with lock:
                results.append(ok)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 50)
        self.assertTrue(all(results))
        self.assertEqual(cb.counters["successful"], 50)

    def test_single_probe_in_half_open(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_timeout=1, clock=clock)
        with self.assertRaises(ValueError):
            cb.call(fail)
        clock.advance(1)
        # Force HALF_OPEN
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)
        gate = threading.Event()
        started = threading.Event()

        def slow_ok():
            started.set()
            gate.wait(timeout=2)
            return "ok"

        t = threading.Thread(target=lambda: cb.call(slow_ok))
        t.start()
        self.assertTrue(started.wait(timeout=2))
        with self.assertRaises(CircuitOpenError):
            cb.call(succeed)
        gate.set()
        t.join(timeout=2)
        self.assertFalse(t.is_alive())


if __name__ == "__main__":
    unittest.main()

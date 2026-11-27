"""Tests for resilience_kit.retry."""

import random
import unittest

from resilience_kit.retry import (
    Retry,
    constant_backoff,
    exponential_backoff,
    retry,
    with_jitter,
)


class TestBackoff(unittest.TestCase):
    def test_exponential(self):
        fn = exponential_backoff(initial=1, multiplier=2, maximum=10)
        self.assertEqual(fn(1), 1)
        self.assertEqual(fn(2), 2)
        self.assertEqual(fn(3), 4)
        self.assertEqual(fn(10), 10)

    def test_constant(self):
        self.assertEqual(constant_backoff(0.5)(7), 0.5)

    def test_jitter_none(self):
        fn = with_jitter(lambda _: 2, jitter="none")
        self.assertEqual(fn(1), 2)

    def test_jitter_full_bounds(self):
        rng = random.Random(42)
        fn = with_jitter(lambda _: 10, jitter="full", rng=rng)
        for _ in range(50):
            self.assertGreaterEqual(fn(1), 0)
            self.assertLessEqual(fn(1), 10)

    def test_jitter_equal_bounds(self):
        rng = random.Random(42)
        fn = with_jitter(lambda _: 10, jitter="equal", rng=rng)
        for _ in range(50):
            self.assertGreaterEqual(fn(1), 5)
            self.assertLessEqual(fn(1), 10)

    def test_validation(self):
        with self.assertRaises(ValueError):
            exponential_backoff(initial=0)
        with self.assertRaises(ValueError):
            with_jitter(lambda _: 1, jitter="bad")


class TestRetry(unittest.TestCase):
    def test_succeeds_first_try(self):
        calls = []

        def f():
            calls.append(1)
            return "ok"

        self.assertEqual(Retry(attempts=3, backoff=lambda _: 0).call(f), "ok")
        self.assertEqual(len(calls), 1)

    def test_succeeds_after_retries(self):
        state = {"n": 0}

        def f():
            state["n"] += 1
            if state["n"] < 3:
                raise ValueError("not yet")
            return "ok"

        policy = Retry(attempts=3, backoff=lambda _: 0)
        self.assertEqual(policy.call(f), "ok")
        self.assertEqual(state["n"], 3)
        self.assertEqual(policy.counters["retries"], 2)

    def test_exhausts_and_reraises(self):
        state = {"n": 0}

        def f():
            state["n"] += 1
            raise ValueError("always")

        policy = Retry(attempts=3, backoff=lambda _: 0)
        with self.assertRaises(ValueError):
            policy.call(f)
        self.assertEqual(state["n"], 3)
        self.assertEqual(policy.counters["exhausted"], 1)

    def test_exception_filter(self):
        state = {"n": 0}

        def f():
            state["n"] += 1
            raise TypeError("not retried")

        with self.assertRaises(TypeError):
            Retry(attempts=3, backoff=lambda _: 0, exceptions=ValueError).call(f)
        self.assertEqual(state["n"], 1)

    def test_on_retry_callback(self):
        events = []

        def f():
            raise ValueError("x")

        policy = Retry(attempts=3, backoff=lambda a: 0.25 * a, on_retry=lambda e, a, d: events.append((a, d)))
        with self.assertRaises(ValueError):
            policy.call(f)
        self.assertEqual(events, [(1, 0.25), (2, 0.5)])

    def test_sleep_called(self):
        sleeps = []

        def f():
            raise ValueError("x")

        policy = Retry(attempts=3, backoff=lambda a: 0.1 * a, sleep=sleeps.append)
        with self.assertRaises(ValueError):
            policy.call(f)
        self.assertEqual(sleeps, [0.1, 0.2])

    def test_decorator(self):
        state = {"n": 0}

        @Retry(attempts=2, backoff=lambda _: 0)
        def f():
            state["n"] += 1
            if state["n"] == 1:
                raise ValueError("x")
            return 42

        self.assertEqual(f(), 42)

    def test_retry_alias(self):
        @retry(attempts=2, backoff=lambda _: 0)
        def f():
            return 1

        self.assertEqual(f(), 1)

    def test_validation(self):
        with self.assertRaises(ValueError):
            Retry(attempts=0)


if __name__ == "__main__":
    unittest.main()

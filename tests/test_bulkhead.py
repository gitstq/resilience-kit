"""Tests for resilience_kit.bulkhead."""

import threading
import time
import unittest

from resilience_kit.bulkhead import Bulkhead, BulkheadFull


class TestBulkhead(unittest.TestCase):
    def test_validation(self):
        with self.assertRaises(ValueError):
            Bulkhead(0)
        with self.assertRaises(ValueError):
            Bulkhead(1, max_wait=-1)

    def test_basic_call(self):
        bh = Bulkhead(limit=2, max_wait=0)
        self.assertEqual(bh.call(lambda: "ok"), "ok")
        self.assertEqual(bh.in_flight, 0)
        self.assertEqual(bh.counters["accepted"], 1)

    def test_limits_concurrency(self):
        bh = Bulkhead(limit=2, max_wait=0)
        gate = threading.Event()
        started = threading.Event()
        results = []
        lock = threading.Lock()

        def worker():
            def task():
                started.set()
                gate.wait(timeout=2)
                return 1

            try:
                r = bh.call(task)
            except BulkheadFull:
                r = "rejected"
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        time.sleep(0.1)
        gate.set()
        for t in threads:
            t.join(timeout=3)
        self.assertEqual(results.count("rejected"), 3)
        self.assertEqual(results.count(1), 2)
        self.assertEqual(bh.in_flight, 0)

    def test_release_on_exception(self):
        bh = Bulkhead(limit=1, max_wait=0)

        def boom():
            raise ValueError("x")

        with self.assertRaises(ValueError):
            bh.call(boom)
        self.assertEqual(bh.in_flight, 0)
        self.assertTrue(bh.try_acquire())
        bh.release()

    def test_wait_for_slot(self):
        bh = Bulkhead(limit=1, max_wait=1)
        self.assertTrue(bh.try_acquire())
        started = time.monotonic()
        self.assertFalse(bh.try_acquire())
        self.assertLess(time.monotonic() - started, 0.5)
        bh.release()

    def test_acquire_with_timeout(self):
        bh = Bulkhead(limit=1)
        self.assertTrue(bh.try_acquire())
        self.assertFalse(bh.acquire(timeout=0.05))
        self.assertEqual(bh.counters["rejected"], 1)
        bh.release()

    def test_decorator(self):
        bh = Bulkhead(limit=1, max_wait=0)

        @bh
        def f(x):
            return x * 2

        self.assertEqual(f(3), 6)


if __name__ == "__main__":
    unittest.main()

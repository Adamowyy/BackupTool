#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Postęp w kolejce UI: limit wysyłki i ograniczony drenaż."""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app


class ProgressSenderTest(unittest.TestCase):
    def test_limits_burst_to_one_message(self):
        sent = []
        send = app.progress_sender("b1", sent.append)
        for index in range(250_000):
            send(index + 1, 250_000, f"map/{index}.bin")
        self.assertLessEqual(len(sent), 4)

    def test_phase_messages_always_pass(self):
        sent = []
        send = app.progress_sender("b1", sent.append)
        send(0, 0, "Skanowanie plików…")
        for percent in (0, 5, 37, 100):
            send(percent, 100, f"upload:{percent}")
        kinds = [payload[3] for _, payload in sent]
        self.assertEqual(kinds[0], "Skanowanie plików…")
        self.assertEqual(kinds[1:], ["upload:0", "upload:5", "upload:37", "upload:100"])

    def test_payload_shape_matches_poll_queue(self):
        sent = []
        app.progress_sender("b1", sent.append)(7, 20, "a.txt")
        kind, payload = sent[0]
        self.assertEqual(kind, "progress")
        self.assertEqual(payload, ("b1", 7, 20, "a.txt"))


class _FakeRoot:
    def __init__(self):
        self.calls = []

    def after(self, delay, callback):
        self.calls.append(delay)


class PollQueueTest(unittest.TestCase):
    def _app(self, items):
        instance = object.__new__(app.BackupApp)
        instance._queue = queue.Queue()
        for payload in items:
            instance._queue.put(("progress", payload))
        instance.root = _FakeRoot()
        instance.seen = []
        instance._show_progress = lambda *args: instance.seen.append(args)
        return instance

    def test_drains_at_most_one_batch_per_tick(self):
        items = [("b1", index, 1000, f"f{index}") for index in range(100)]
        instance = self._app(items)
        instance._poll_queue()
        self.assertEqual(len(instance.seen), app.PROGRESS_PER_TICK)
        self.assertEqual(instance.root.calls, [1])

    def test_drains_rest_on_next_tick(self):
        items = [("b1", index, 1000, f"f{index}") for index in range(100)]
        instance = self._app(items)
        for _ in range(5):
            instance._poll_queue()
        self.assertEqual(len(instance.seen), 100)
        self.assertTrue(instance._queue.empty())
        self.assertEqual(instance.root.calls[-1], 80)

    def test_slow_tick_keeps_normal_delay(self):
        instance = self._app([("b1", 1, 10, "a.txt")])
        instance._poll_queue()
        self.assertEqual(instance.root.calls, [80])


if __name__ == "__main__":
    unittest.main()

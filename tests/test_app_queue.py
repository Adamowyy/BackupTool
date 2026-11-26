#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wybór backupów do uruchomienia i kolejka w trakcie trwającego przebiegu."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
import backup_core as core
import i18n


class _FakeRoot:
    def __init__(self):
        self.calls = []

    def after(self, delay, callback):
        self.calls.append(delay)


class QueueTest(unittest.TestCase):
    def setUp(self):
        self._language = i18n.language()
        i18n.set_language("en")
        self.root_dir = tempfile.mkdtemp(prefix="bt-queue-")
        self.source = os.path.join(self.root_dir, "src")
        self.dest = os.path.join(self.root_dir, "dest")
        os.makedirs(self.source)
        os.makedirs(self.dest)
        self.backups = [self._backup("a", "Alpha"), self._backup("b", "Beta"),
                        self._backup("c", "Gamma")]
        self.instance = self._app()

    def tearDown(self):
        i18n.set_language(self._language)
        shutil.rmtree(self.root_dir, ignore_errors=True)

    def _backup(self, backup_id, name):
        return {"id": backup_id, "name": name, "sources": [self.source],
                "destination": self.dest, "use_zip": True,
                "app_data": {"hermes": False, "obsidian": False, "memory": "mnemosyne"},
                "cloud": {"provider": "none", "path": "", "paths": {}}}

    def _app(self):
        instance = object.__new__(app.BackupApp)
        instance.state = {"version": 1, "backups": self.backups}
        instance._selected = set()
        instance._batch_queue = []
        instance._batch_total = 0
        instance._batch_ok = 0
        instance._batch_errors = 0
        instance._running_id = None
        instance._downloading = None
        instance.root = _FakeRoot()
        instance.statuses = []
        instance.refreshes = 0
        instance._set_status = lambda text, color=None: instance.statuses.append(text)
        instance._refresh_list = lambda: setattr(instance, "refreshes",
                                                 instance.refreshes + 1)
        return instance

    def test_enqueue_during_single_run_grows_the_series(self):
        self.instance._running_id = "a"
        self.assertTrue(self.instance._enqueue("b"))
        self.assertEqual(self.instance._batch_queue, ["b"])
        self.assertEqual(self.instance._batch_total, 2)

    def test_enqueue_ignores_the_running_backup_and_duplicates(self):
        self.instance._running_id = "a"
        self.assertFalse(self.instance._enqueue("a"))
        self.assertTrue(self.instance._enqueue("b"))
        self.assertFalse(self.instance._enqueue("b"))
        self.assertEqual(self.instance._batch_queue, ["b"])
        self.assertEqual(self.instance._batch_total, 2)

    def test_enqueue_rejects_a_backup_that_cannot_run(self):
        broken = {"id": "d", "name": "Broken", "sources": [],
                  "destination": self.dest, "cloud": {"provider": "none"}}
        self.instance.state["backups"].append(broken)
        self.instance._running_id = "a"
        self.assertFalse(self.instance._enqueue("d"))
        self.assertEqual(self.instance._batch_queue, [])

    def test_unqueue_removes_and_keeps_the_series_counter_alive(self):
        self.instance._running_id = "a"
        self.instance._enqueue("b")
        self.instance._unqueue("b")
        self.assertEqual(self.instance._batch_queue, [])
        self.assertEqual(self.instance._batch_total, 1)

    def test_start_run_on_another_row_enqueues_instead_of_starting(self):
        self.instance._running_id = "a"
        added = []
        self.instance._enqueue = lambda bid, quiet=False: added.append(bid) or True
        self.instance._start_run("b")
        self.assertEqual(added, ["b"])

    def test_start_run_on_the_running_row_does_nothing(self):
        self.instance._running_id = "a"
        added = []
        self.instance._enqueue = lambda bid, quiet=False: added.append(bid) or True
        self.instance._start_run("a")
        self.assertEqual(added, [])

    def test_run_selected_queues_when_busy(self):
        self.instance._running_id = "a"
        self.instance._selected = {"b", "c"}
        self.instance._run_selected()
        self.assertEqual(self.instance._batch_queue, ["b", "c"])
        self.assertEqual(self.instance._batch_total, 3)
        self.assertEqual(self.instance._selected, set())

    def test_selected_ids_follow_the_list_order(self):
        self.instance._selected = {"c", "a"}
        self.assertEqual(self.instance._selected_ids(), ["a", "c"])

    def test_queued_badge_is_visible(self):
        self.instance._batch_queue = ["b"]
        self.assertEqual(self.instance._badge_for(self.backups[1])[0],
                         i18n.t("Queued…"))
        self.assertNotEqual(self.instance._badge_for(self.backups[0])[0],
                            i18n.t("Queued…"))

    def test_single_run_finish_keeps_the_plain_status(self):
        self.instance._running_id = "a"
        self.instance._batch_total = 1
        self.instance._batch_ok = 1
        self.instance._batch_next()
        self.assertEqual(self.instance._batch_total, 0)
        self.assertEqual(self.instance.statuses, [])


if __name__ == "__main__":
    unittest.main()

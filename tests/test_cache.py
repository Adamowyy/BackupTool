#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sprzątanie map i staging po backupach, których nie ma już na liście."""

import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup_core as core


class PurgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-purge-")
        self.staging = os.path.join(self.tmp, "staging")
        self.manifests = os.path.join(self.tmp, "manifests")
        os.makedirs(self.staging)
        os.makedirs(self.manifests)
        for name, target in (("staging_root", self.staging),
                             ("manifest_root", self.manifests)):
            patcher = mock.patch.object(core, name, lambda p=target: p)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def _entry(self, ident, payload=b"x" * 1000):
        folder = os.path.join(self.staging, ident)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "kopia.zip"), "wb") as handle:
            handle.write(payload)
        with open(os.path.join(self.manifests, ident + ".json.gz"), "wb") as handle:
            handle.write(payload)

    def test_kept_backup_survives(self):
        self._entry("aaa")
        removed, freed = core.purge_stale(["aaa"])
        self.assertEqual((removed, freed), (0, 0))
        self.assertTrue(os.path.isdir(os.path.join(self.staging, "aaa")))
        self.assertTrue(os.path.isfile(os.path.join(self.manifests, "aaa.json.gz")))

    def test_orphans_are_removed_with_their_size(self):
        self._entry("aaa")
        self._entry("bbb")
        removed, freed = core.purge_stale(["aaa"])
        self.assertEqual(removed, 2, "staging + manifest")
        self.assertEqual(freed, 2000)
        self.assertTrue(os.path.isdir(os.path.join(self.staging, "aaa")))
        self.assertFalse(os.path.exists(os.path.join(self.staging, "bbb")))
        self.assertFalse(os.path.exists(os.path.join(self.manifests, "bbb.json.gz")))

    def test_recent_orphan_is_left_alone_until_it_ages(self):
        self._entry("ccc")
        removed, _freed = core.purge_stale(["aaa"], older_than_days=7)
        self.assertEqual(removed, 0, "świeżo usunięty backup może wrócić z listy")
        old = time.time() - 30 * 86400
        os.utime(os.path.join(self.staging, "ccc"), (old, old))
        os.utime(os.path.join(self.manifests, "ccc.json.gz"), (old, old))
        removed, _freed = core.purge_stale(["aaa"], older_than_days=7)
        self.assertEqual(removed, 2)

    def test_foreign_names_are_ignored(self):
        for name in ("not-an-id.txt", "keepme", "x" * 40):
            with open(os.path.join(self.manifests, name), "wb") as handle:
                handle.write(b"x")
        removed, _freed = core.purge_stale([])
        self.assertEqual(removed, 0)
        self.assertEqual(len(os.listdir(self.manifests)), 3)


if __name__ == "__main__":
    unittest.main()

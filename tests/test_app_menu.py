#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pozycje menu aplikacji (kopia/przywracanie listy)."""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app
import cloud
import i18n


class MenuItemsTest(unittest.TestCase):
    def setUp(self):
        self._language = i18n.language()
        i18n.set_language("en")
        self.instance = object.__new__(app.BackupApp)
        for name in ("_save_list_local", "_restore_list_local"):
            setattr(self.instance, name, lambda: None)
        for name in ("_save_list_cloud", "_restore_list_cloud"):
            setattr(self.instance, name, lambda provider=None: None)

    def tearDown(self):
        i18n.set_language(self._language)

    def _items(self, ready):
        with mock.patch.object(cloud, "remote_ready", side_effect=ready):
            return self.instance._menu_items()

    def test_both_sections_with_a_connected_cloud(self):
        items = self._items(lambda name: name == "gdrive")
        self.assertEqual([t for t, _c, _e in items],
                         ["Backup list", "Local…", "Google Drive",
                          "Restore list", "Local…", "Google Drive",
                          "Application", "About", "Check for updates"])
        self.assertIsNone(items[0][1], "nagłówek nie ma komendy")
        self.assertTrue(all(callable(c) for _t, c, _e in items if c))

    def test_without_account_each_section_says_so(self):
        items = self._items(lambda name: False)
        disabled = [t for t, c, e in items if e is False]
        self.assertEqual(len(disabled), 2)
        self.assertTrue(all("no account" in text for text in disabled))

    def test_cloud_commands_carry_their_provider(self):
        seen = []
        self.instance._save_list_cloud = lambda provider=None: seen.append(provider)
        items = self._items(lambda name: True)
        items[2][1]()
        self.assertEqual(seen, ["dropbox"])


if __name__ == "__main__":
    unittest.main()

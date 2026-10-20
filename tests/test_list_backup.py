#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy pliku listy backupów: zapis, odczyt, chmura (rclone mockowany)."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup_core as core
import cloud
import i18n
import list_backup


def write(path, content="x"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class ListPayloadTests(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")
        self.tmp = tempfile.mkdtemp(prefix="bt-list-")
        self.source = os.path.join(self.tmp, "Photos")
        os.makedirs(self.source)

    def tearDown(self):
        i18n.set_language("en")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _state(self):
        state = core.default_state()
        backup = core.new_backup("Photos", [self.source], "D:/Out", True,
                                 cloud_settings={"provider": "dropbox",
                                                 "path": "BackupTool/Photos"})
        core.put_backup(state, backup)
        return state

    def test_payload_carries_header(self):
        payload = list_backup.build_payload(self._state())
        self.assertEqual(payload["kind"], list_backup.PAYLOAD_KIND)
        self.assertTrue(payload["created_at"])
        self.assertEqual(len(payload["backups"]), 1)
        self.assertIsNot(payload["backups"][0], self._state()["backups"][0])

    def test_roundtrip_keeps_settings(self):
        state = self._state()
        original = state["backups"][0]
        path = os.path.join(self.tmp, "list.json")
        list_backup.dump_payload(list_backup.build_payload(state), path)
        loaded = list_backup.read_payload(path)

        self.assertEqual(len(loaded["backups"]), 1)
        restored = loaded["backups"][0]
        self.assertEqual(restored["id"], original["id"])
        self.assertEqual(restored["name"], "Photos")
        self.assertEqual(restored["sources"], [self.source])
        self.assertEqual(restored["destination"], "D:/Out")
        self.assertTrue(restored["use_zip"])
        self.assertEqual(core.cloud_provider(restored), "dropbox")
        self.assertEqual(core.cloud_remote_dir(restored), "BackupTool/Photos")

    def test_dump_creates_missing_folders(self):
        path = os.path.join(self.tmp, "a", "b", "list.json")
        list_backup.dump_payload(list_backup.build_payload(self._state()), path)
        self.assertTrue(os.path.isfile(path))

    def test_dump_reports_unwritable_path(self):
        blocker = write(os.path.join(self.tmp, "blocker"), "x")
        with self.assertRaises(list_backup.ListError):
            list_backup.dump_payload({"backups": []},
                                     os.path.join(blocker, "list.json"))

    def test_read_rejects_broken_json(self):
        path = write(os.path.join(self.tmp, "broken.json"), "{not json")
        with self.assertRaises(list_backup.ListError):
            list_backup.read_payload(path)

    def test_read_rejects_foreign_file(self):
        path = write(os.path.join(self.tmp, "other.json"),
                     json.dumps({"kind": "something-else", "backups": []}))
        with self.assertRaises(list_backup.ListError) as caught:
            list_backup.read_payload(path)
        self.assertIn("not a BackupTool list", str(caught.exception))

    def test_read_rejects_empty_list(self):
        path = write(os.path.join(self.tmp, "empty.json"),
                     json.dumps({"kind": list_backup.PAYLOAD_KIND, "backups": []}))
        with self.assertRaises(list_backup.ListError):
            list_backup.read_payload(path)

    def test_read_cleans_foreign_fields(self):
        path = write(os.path.join(self.tmp, "hand-made.json"), json.dumps({
            "backups": [{"name": "Ręczna", "sources": [self.source],
                         "destination": "D:/Out", "evil": {"x": 1}}]}))
        restored = list_backup.read_payload(path)["backups"][0]
        self.assertEqual(restored["name"], "Ręczna")
        self.assertNotIn("evil", restored)
        self.assertEqual(core.cloud_provider(restored), "none")
        self.assertTrue(restored["id"])

    def test_suggested_filename_has_today(self):
        name = list_backup.suggested_filename()
        self.assertRegex(name, r"^backup-list-\d{4}-\d{2}-\d{2}\.json$")

    def test_missing_sources_counts_only_absent_paths(self):
        backups = [{"sources": [self.source, os.path.join(self.tmp, "gone")]},
                   {"sources": [self.source]},
                   {"sources": []}]
        self.assertEqual(list_backup.missing_sources(backups), 1)
        self.assertEqual(list_backup.missing_sources([]), 0)

    def test_error_message_is_translated(self):
        i18n.set_language("pl")
        with self.assertRaises(list_backup.ListError) as caught:
            list_backup.read_payload(os.path.join(self.tmp, "brak.json"))
        self.assertTrue(str(caught.exception).startswith("Nie udało się odczytać listy"))


class ListCloudTests(unittest.TestCase):
    """Wymiana listy z chmurą: rclone mockowany, bez sieci i konta."""

    def setUp(self):
        i18n.set_language("en")
        self.tmp = tempfile.mkdtemp(prefix="bt-list-cloud-")
        self.payload = {"kind": list_backup.PAYLOAD_KIND, "version": 1,
                        "created_at": "2026-10-20T10:00:00",
                        "backups": [core.new_backup("Photos", [], "D:/Out")]}
        self.info = {"name": list_backup.LIST_FILE, "size": 512,
                     "modified": "2026-10-20T10:05:00.000Z"}

    def tearDown(self):
        i18n.set_language("en")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_upload_sends_one_list_file_and_verifies_it(self):
        seen = {}

        def fake_upload(local, provider, remote_dir, on_status=None,
                        on_percent=None, should_stop=None):
            seen.update(local=local, provider=provider, remote_dir=remote_dir)
            with open(local, "r", encoding="utf-8") as handle:
                seen["payload"] = json.load(handle)

        with mock.patch.object(cloud, "upload_file", side_effect=fake_upload), \
                mock.patch.object(cloud, "remote_file", return_value=self.info):
            info = list_backup.cloud_upload(self.payload, "dropbox")

        self.assertEqual(info["size"], 512)
        self.assertEqual(seen["provider"], "dropbox")
        self.assertEqual(seen["remote_dir"], list_backup.LIST_FOLDER)
        self.assertEqual(os.path.basename(seen["local"]), list_backup.LIST_FILE)
        self.assertEqual(seen["payload"]["backups"][0]["name"], "Photos")
        self.assertFalse(os.path.exists(os.path.dirname(seen["local"])))

    def test_upload_fails_when_cloud_has_no_file(self):
        with mock.patch.object(cloud, "upload_file"), \
                mock.patch.object(cloud, "remote_file", return_value=None):
            with self.assertRaises(list_backup.ListError) as caught:
                list_backup.cloud_upload(self.payload, "gdrive")
        self.assertIn("did not reach", str(caught.exception))

    def test_upload_wraps_cloud_error(self):
        with mock.patch.object(cloud, "upload_file",
                               side_effect=cloud.CloudError("boom")):
            with self.assertRaises(list_backup.ListError) as caught:
                list_backup.cloud_upload(self.payload, "dropbox")
        self.assertIn("boom", str(caught.exception))

    def test_download_reads_the_cloud_list(self):
        def fake_download(local, provider, remote_dir, filename,
                          on_percent=None, should_stop=None):
            write(local, json.dumps(self.payload))

        with mock.patch.object(cloud, "remote_file", return_value=self.info), \
                mock.patch.object(cloud, "download_file", side_effect=fake_download):
            got = list_backup.cloud_download("dropbox")

        self.assertEqual(len(got["backups"]), 1)
        self.assertEqual(got["backups"][0]["name"], "Photos")
        self.assertEqual(got["info"]["size"], 512)

    def test_download_without_a_cloud_list_explains_it(self):
        with mock.patch.object(cloud, "remote_file", return_value=None):
            with self.assertRaises(list_backup.ListError) as caught:
                list_backup.cloud_download("dropbox")
        self.assertIn("No list in the cloud yet", str(caught.exception))


class RestoreUiTests(unittest.TestCase):
    """Przywrócenie listy w UI bez okna Tk (obiekt aplikacji na sucho)."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as app_module
        except Exception:  # pragma: no cover - brak GUI w środowisku testowym
            raise unittest.SkipTest("customtkinter not available")
        cls.app_module = app_module

    def setUp(self):
        i18n.set_language("en")
        self.tmp = tempfile.mkdtemp(prefix="bt-list-restore-")

    def tearDown(self):
        i18n.set_language("en")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bare_app(self, backups=None):
        instance = object.__new__(self.app_module.BackupApp)
        instance.root = mock.Mock()
        instance.state = {"version": 1, "backups": list(backups or []),
                          "language": "en"}
        instance._ready_this_session = {"old-id"}
        instance.status = mock.Mock()
        instance.last = None
        instance._refresh_list = mock.Mock()
        instance._set_status = lambda text, color=None: setattr(
            instance, "last", (text, color))
        return instance

    def _payload(self, backups):
        return {"backups": backups, "created_at": ""}

    def test_restore_replaces_the_list(self):
        instance = self._bare_app([core.new_backup("Stary", [], "D:/Old")])
        incoming = [core.new_backup("Nowy", [], "D:/New"),
                    core.new_backup("Drugi", [], "D:/Two")]
        with mock.patch.object(self.app_module.messagebox, "askyesno",
                               return_value=True), \
                mock.patch.object(core, "save_state") as save:
            instance._confirm_restore(self._payload(incoming), "backup-list.json")

        self.assertEqual([b["name"] for b in instance.state["backups"]],
                         ["Nowy", "Drugi"])
        save.assert_called_once()
        self.assertEqual(instance._ready_this_session, set())
        instance._refresh_list.assert_called_once()
        self.assertIn("Restored the list: 2 backups", instance.last[0])

    def test_cancelled_restore_keeps_the_old_list(self):
        old = core.new_backup("Stary", [], "D:/Old")
        instance = self._bare_app([old])
        with mock.patch.object(self.app_module.messagebox, "askyesno",
                               return_value=False):
            instance._confirm_restore(
                self._payload([core.new_backup("Nowy", [], "D:/New")]), "plik")

        self.assertEqual(instance.state["backups"], [old])
        self.assertIn("cancelled", instance.last[0])

    def test_restore_warns_about_missing_sources(self):
        instance = self._bare_app()
        incoming = [core.new_backup("Nowy", [os.path.join(self.tmp, "brak")],
                                    "D:/New")]
        with mock.patch.object(self.app_module.messagebox, "askyesno",
                               return_value=True), \
                mock.patch.object(core, "save_state"):
            instance._confirm_restore(self._payload(incoming), "plik")

        self.assertIn("sources are missing", instance.last[0])
        self.assertEqual(instance.last[1], self.app_module.WARN_TEXT)


class NeedsSetupUiTests(unittest.TestCase):
    """Wiersz „Wymaga konfiguracji” zamiast błędu dopiero po kliknięciu Start."""

    @classmethod
    def setUpClass(cls):
        try:
            import app as app_module
        except Exception:  # pragma: no cover - brak GUI w środowisku testowym
            raise unittest.SkipTest("customtkinter not available")
        cls.app_module = app_module

    def setUp(self):
        i18n.set_language("en")
        self.tmp = tempfile.mkdtemp(prefix="bt-needs-setup-")
        self.source = os.path.join(self.tmp, "Photos")
        os.makedirs(self.source)

    def tearDown(self):
        i18n.set_language("en")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _bare(self):
        instance = object.__new__(self.app_module.BackupApp)
        instance._running_id = None
        instance._downloading = None
        instance._ready_this_session = set()
        instance.calls = []
        instance._set_status = lambda text, color=None: instance.calls.append(("status", text))
        instance._edit_backup = lambda bid: instance.calls.append(("edit", bid))
        return instance

    def test_missing_source_gets_red_setup_badge(self):
        backup = core.new_backup("Photos", [os.path.join(self.tmp, "gone")], "D:/Out")
        problem = core.setup_problem(backup)
        self.assertTrue(problem)
        badge = self._bare()._badge_for(backup, problem)
        self.assertEqual(badge, ("Needs setup", self.app_module.STALE_BG,
                                 self.app_module.STALE_TEXT))

    def test_healthy_backup_keeps_its_badge(self):
        backup = core.new_backup("Photos", [self.source], "D:/Out")
        self.assertIsNone(core.setup_problem(backup))
        self.assertEqual(self._bare()._badge_for(backup, None)[0], "New")

    def test_running_row_still_shows_running(self):
        backup = core.new_backup("Photos", [os.path.join(self.tmp, "gone")], "D:/Out")
        instance = self._bare()
        instance._running_id = backup["id"]
        badge = instance._badge_for(backup, core.setup_problem(backup))
        self.assertEqual(badge[0], "Running…")

    def test_setup_button_shows_reason_then_opens_settings(self):
        instance = self._bare()
        instance._fix_backup("id-7", "Source not found: D:\\x")
        self.assertEqual(instance.calls[0], ("status", "Source not found: D:\\x"))
        self.assertEqual(instance.calls[1], ("edit", "id-7"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

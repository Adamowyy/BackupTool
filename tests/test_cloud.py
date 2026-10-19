#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy integracji chmury (rclone mockowany — bez sieci i bez konta)."""

import os
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup_core as core
import cloud
import i18n


def write(path, content="x"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class CloudModelTests(unittest.TestCase):
    def test_default_is_local(self):
        self.assertEqual(core.normalize_cloud(None),
                         {"provider": "none", "path": ""})
        self.assertEqual(core.cloud_provider({}), "none")

    def test_known_providers(self):
        for provider in ("dropbox", "gdrive"):
            self.assertEqual(core.normalize_cloud({"provider": provider})["provider"], provider)

    def test_unknown_provider_falls_back_to_local(self):
        self.assertEqual(core.normalize_cloud({"provider": "onedrive"})["provider"], "none")

    def test_new_backup_carries_cloud(self):
        backup = core.new_backup("A", [], "D:/x", True,
                                 cloud_settings={"provider": "dropbox"})
        self.assertEqual(backup["cloud"]["provider"], "dropbox")

    def test_empty_remote_dir_means_account_root(self):
        backup = core.new_backup("Moje rzeczy", [], "", True,
                                 cloud_settings={"provider": "dropbox"})
        self.assertEqual(core.cloud_remote_dir(backup), "")
        self.assertEqual(core.display_target(backup), "Dropbox  →  Moje rzeczy.zip")

    def test_remote_dir_custom_path_is_normalised(self):
        backup = core.new_backup("A", [], "", True,
                                 cloud_settings={"provider": "gdrive",
                                                 "path": "\\Kopie\\BackupTool\\"})
        self.assertEqual(core.cloud_remote_dir(backup), "Kopie/BackupTool")


class CloudTargetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-cloud-")
        self.source = write(os.path.join(self.tmp, "src", "a.txt"), "A")

    def test_target_for_cloud_lives_in_staging(self):
        backup = core.new_backup("Kopia", [self.source], "", True,
                                 cloud_settings={"provider": "dropbox"})
        target = core.target_path(backup)
        self.assertTrue(target.startswith(core.staging_root()), target)
        self.assertTrue(target.endswith("Kopia.zip"))

    def test_display_target_names_provider(self):
        backup = core.new_backup("Kopia", [self.source], "", True,
                                 cloud_settings={"provider": "dropbox"})
        self.assertEqual(core.display_target(backup), "Dropbox  →  Kopia.zip")

    def test_local_display_target_is_plain_path(self):
        backup = core.new_backup("Kopia", [self.source], self.tmp, True)
        self.assertEqual(core.display_target(backup),
                         os.path.join(self.tmp, "Kopia.zip"))


class CloudValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-cloudval-")
        self.source = write(os.path.join(self.tmp, "src", "a.txt"), "A")
        self.backup = core.new_backup("Kopia", [self.source], "", True,
                                      cloud_settings={"provider": "dropbox"})

    def test_not_connected_blocks_backup(self):
        with mock.patch.object(cloud, "remote_ready", return_value=False):
            error = core.validate_backup(self.backup)
        self.assertIn("nie jest połączone", error)

    def test_connected_accepts_empty_local_destination(self):
        with mock.patch.object(cloud, "remote_ready", return_value=True):
            self.assertIsNone(core.validate_backup(self.backup))


class CloudRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-cloudrun-")
        self.source = write(os.path.join(self.tmp, "src", "a.txt"), "A")
        self.uploaded = []

    def _backup(self, **cloud_data):
        data = {"provider": "dropbox"}
        data.update(cloud_data)
        return core.new_backup("Kopia", [self.source], "", True, cloud_settings=data)

    def test_zip_is_uploaded_and_staging_removed(self):
        backup = self._backup()

        def fake_upload(backup_arg, local_target, on_status=None, on_percent=None, should_stop=None):
            self.uploaded.append(local_target)
            self.assertTrue(os.path.isfile(local_target))
            with zipfile.ZipFile(local_target) as archive:
                self.assertIn("a.txt", [n.replace("\\", "/") for n in archive.namelist()])
            return False

        with mock.patch.object(cloud, "remote_ready", return_value=True), \
                mock.patch.object(cloud, "prepare_upload", side_effect=fake_upload):
            result = core.run_backup(backup)

        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(result["target"], "Dropbox  →  Kopia.zip")
        self.assertEqual(len(self.uploaded), 1)
        self.assertFalse(os.path.exists(core.staging_path(backup)))

    def test_cloud_ignores_folder_mode_and_always_zips(self):
        backup = core.new_backup("Kopia", [self.source], "", False,
                                 cloud_settings={"provider": "gdrive"})
        seen = {}

        def fake_upload(backup_arg, local_target, on_status=None, on_percent=None, should_stop=None):
            seen["is_file"] = os.path.isfile(local_target)
            seen["name"] = os.path.basename(local_target)
            return False

        with mock.patch.object(cloud, "remote_ready", return_value=True), \
                mock.patch.object(cloud, "prepare_upload", side_effect=fake_upload):
            result = core.run_backup(backup)

        self.assertTrue(result["ok"], result["message"])
        self.assertTrue(seen["is_file"])
        self.assertTrue(seen["name"].endswith(".zip"))
        self.assertEqual(result["target"], "Google Drive  →  Kopia.zip")
        self.assertFalse(os.path.exists(core.staging_path(backup)))

    def test_upload_error_is_reported_and_staging_cleaned(self):
        backup = self._backup()

        def failing(backup_arg, local_target, on_status=None, on_percent=None, should_stop=None):
            raise cloud.CloudError("Konto zostało odłączone — połącz je ponownie.")

        with mock.patch.object(cloud, "remote_ready", return_value=True), \
                mock.patch.object(cloud, "prepare_upload", side_effect=failing):
            result = core.run_backup(backup)

        self.assertFalse(result["ok"])
        self.assertIn("odłączone", result["message"])
        self.assertFalse(os.path.exists(core.staging_path(backup)))

    def test_local_folder_mode_still_copies_folder(self):
        backup = core.new_backup("Kopia", [self.source], self.tmp, False)
        with mock.patch.object(cloud, "prepare_upload") as upload:
            result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        upload.assert_not_called()
        self.assertFalse(result["target"].endswith(".zip"))
        self.assertTrue(os.path.isdir(result["target"]))

    def test_local_backup_does_not_touch_cloud(self):
        backup = core.new_backup("Lokalny", [self.source], self.tmp, True)
        with mock.patch.object(cloud, "prepare_upload") as upload:
            result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        upload.assert_not_called()


class RcloneConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-rclone-")
        self.conf = os.path.join(self.tmp, "rclone.conf")
        self.env = mock.patch.dict(os.environ, {"BACKUPTOOL_RCLONE_CONF": self.conf})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_remote_not_ready_without_token(self):
        self.assertFalse(cloud.remote_ready("dropbox"))

    def test_token_marks_remote_ready(self):
        parser = cloud._read_conf()
        parser.add_section("dropbox")
        parser.set("dropbox", "type", "dropbox")
        parser.set("dropbox", "token", '{"access_token":"a","refresh_token":"r"}')
        cloud._write_conf(parser)
        self.assertTrue(cloud.remote_ready("dropbox"))
        self.assertFalse(cloud.remote_ready("gdrive"))

    def test_forget_removes_section(self):
        parser = cloud._read_conf()
        parser.add_section("gdrive")
        parser.set("gdrive", "token", '{"refresh_token":"r"}')
        cloud._write_conf(parser)
        cloud.forget("gdrive")
        self.assertFalse(cloud.remote_ready("gdrive"))

    def test_token_extraction_from_authorize_output(self):
        output = ('If your browser doesn\'t open...\n2026/10/18 NOTICE: Config file not found\n'
                  '{"access_token":"ya29.a","token_type":"Bearer",'
                  '"refresh_token":"1//0g","expiry":"2026-10-18T23:00:00+02:00"}\n')
        token = cloud._extract_token(output)
        self.assertEqual(token["refresh_token"], "1//0g")

    def test_garbage_authorize_output_returns_none(self):
        self.assertIsNone(cloud._extract_token("Paste the following into your remote machine --->\n<---End paste"))


class CloudDownloadTests(unittest.TestCase):
    """Sprawdzenie i pobranie kopii z chmury — rclone mockowany, bez sieci."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-dl-")

    def _exe(self):
        return mock.patch.object(cloud, "rclone_exe", return_value="C:/rclone.exe")

    def _ready(self, value=True):
        return mock.patch.object(cloud, "remote_ready", return_value=value)

    def test_remote_file_reports_size_and_date(self):
        payload = ('{"Path":"Kopia.zip","Name":"Kopia.zip","Size":123,'
                   '"ModTime":"2026-10-19T08:18:09.508Z","IsDir":false}')
        completed = mock.Mock(returncode=0, stdout=payload, stderr="")
        with self._ready(), self._exe(), \
                mock.patch.object(cloud.subprocess, "run", return_value=completed) as run:
            info = cloud.remote_file("gdrive", "Backups/Gry", "Kopia.zip")

        self.assertEqual(info["size"], 123)
        self.assertEqual(info["modified"], "2026-10-19T08:18:09.508Z")
        self.assertEqual(run.call_args[0][0][1:4],
                         ["lsjson", "gdrive:Backups/Gry/Kopia.zip", "--stat"])

    def test_remote_file_missing_returns_none(self):
        completed = mock.Mock(
            returncode=3, stdout="",
            stderr="2026/10/19 14:17:33 NOTICE: Failed to lsjson: directory not found\n")
        with self._ready(), self._exe(), \
                mock.patch.object(cloud.subprocess, "run", return_value=completed):
            self.assertIsNone(cloud.remote_file("dropbox", "Backups", "Kopia.zip"))

    def test_remote_file_without_token_raises(self):
        with self._exe(), self._ready(False):
            with self.assertRaises(cloud.CloudError):
                cloud.remote_file("dropbox", "", "Kopia.zip")

    def test_remote_ref_handles_root_and_nested_paths(self):
        self.assertEqual(cloud._remote_ref("dropbox", "", "a.zip"), "dropbox:a.zip")
        self.assertEqual(cloud._remote_ref("gdrive", "/Backups/Gry/", "a.zip"),
                         "gdrive:Backups/Gry/a.zip")
        self.assertEqual(cloud._remote_ref("gdrive", "\\Kopie\\", "a.zip"),
                         "gdrive:Kopie/a.zip")

    def test_download_file_copies_one_archive(self):
        seen = {}

        def fake_run(args, on_percent=None, should_stop=None, action="upload"):
            seen["args"] = list(args)
            seen["action"] = action
            write(args[3], "zip-bytes")

        local = os.path.join(self.tmp, "Kopia.zip")
        with self._exe(), mock.patch.object(cloud, "_run_rclone", side_effect=fake_run):
            cloud.download_file(local, "gdrive", "Backups/Gry", "Kopia.zip")

        self.assertEqual(seen["args"][1:3],
                         ["copyto", "gdrive:Backups/Gry/Kopia.zip"])
        self.assertEqual(seen["args"][3], local)
        self.assertEqual(seen["action"], "download")
        self.assertTrue(os.path.isfile(local))

    def test_download_file_reports_missing_output(self):
        local = os.path.join(self.tmp, "brak.zip")
        with self._exe(), mock.patch.object(cloud, "_run_rclone", return_value=None):
            with self.assertRaises(cloud.CloudError):
                cloud.download_file(local, "gdrive", "", "brak.zip")

    def test_download_creates_missing_target_folder(self):
        local = os.path.join(self.tmp, "nowy", "podfolder", "Kopia.zip")

        def fake_run(args, on_percent=None, should_stop=None, action="upload"):
            write(args[3], "x")

        with self._exe(), mock.patch.object(cloud, "_run_rclone", side_effect=fake_run):
            cloud.download_file(local, "dropbox", "Backups", "Kopia.zip")
        self.assertTrue(os.path.isfile(local))

    def test_cancelled_download_leaves_no_partial_file(self):
        local = os.path.join(self.tmp, "Kopia.zip")
        partial = os.path.join(self.tmp, "Kopia.zip.1dfc9770.partial")
        write(partial, "kawalek")

        def stop_run(args, on_percent=None, should_stop=None, action="upload"):
            raise cloud.CloudError("Przerwano pobieranie.")

        with self._exe(), mock.patch.object(cloud, "_run_rclone", side_effect=stop_run):
            with self.assertRaises(cloud.CloudError):
                cloud.download_file(local, "gdrive", "Backups", "Kopia.zip")

        self.assertFalse(os.path.exists(partial))
        self.assertFalse(os.path.exists(local))

    def test_finished_download_clears_stale_partial(self):
        local = os.path.join(self.tmp, "Kopia.zip")
        partial = os.path.join(self.tmp, "Kopia.zip.deadbeef.partial")
        write(partial, "kawalek")

        def ok_run(args, on_percent=None, should_stop=None, action="upload"):
            write(args[3], "zip")

        with self._exe(), mock.patch.object(cloud, "_run_rclone", side_effect=ok_run):
            cloud.download_file(local, "gdrive", "Backups", "Kopia.zip")
        self.assertFalse(os.path.exists(partial))
        self.assertTrue(os.path.isfile(local))


class DownloadUiHelperTests(unittest.TestCase):
    """Pomocnicze funkcje UI pobierania (bez okna Tk)."""

    @classmethod
    def setUpClass(cls):
        try:
            import threading
            import app  # noqa: F401 - wymaga customtkinter
        except Exception:  # pragma: no cover - brak GUI w środowisku testowym
            raise unittest.SkipTest("customtkinter not available")
        import app as app_module
        cls.helpers = app_module.BackupApp
        cls.threading = threading

    def setUp(self):
        i18n.set_language("pl")
        self.tmp = tempfile.mkdtemp(prefix="bt-dl-name-")

    def tearDown(self):
        i18n.set_language("en")

    def _bare_app(self):
        """Obiekt klasy aplikacji bez budowania okna — do testu samego Stop."""
        instance = object.__new__(self.helpers)
        instance._downloading = "id-1"
        instance._download_cancel = self.threading.Event()
        instance.status = mock.Mock()
        return instance

    def test_stop_sets_the_cancel_flag(self):
        instance = self._bare_app()
        instance._toggle_download("id-1")
        self.assertTrue(instance._download_cancel.is_set())

    def test_stop_ignores_another_row(self):
        instance = self._bare_app()
        instance._toggle_download("id-2")
        self.assertFalse(instance._download_cancel.is_set())

    def test_existing_file_is_not_overwritten(self):
        write(os.path.join(self.tmp, "Kopia.zip"), "stara")
        target = self.helpers._free_download_path(self.tmp, "Kopia.zip")
        self.assertEqual(os.path.basename(target), "Kopia (2).zip")
        write(target, "nowa")
        third = self.helpers._free_download_path(self.tmp, "Kopia.zip")
        self.assertEqual(os.path.basename(third), "Kopia (3).zip")

    def test_free_path_keeps_plain_name_when_empty(self):
        self.assertEqual(os.path.basename(self.helpers._free_download_path(self.tmp, "A.zip")),
                         "A.zip")

    def test_cloud_date_is_shown_in_local_time(self):
        when = self.helpers._cloud_when("2026-10-19T08:18:09.508Z")
        self.assertRegex(when, r"\d{2}:\d{2}")
        self.assertEqual(self.helpers._cloud_when(""), "")
        self.assertEqual(self.helpers._cloud_when("bzdura"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

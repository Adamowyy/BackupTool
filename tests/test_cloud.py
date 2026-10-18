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


if __name__ == "__main__":
    unittest.main(verbosity=2)

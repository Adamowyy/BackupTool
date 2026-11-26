#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aktualizacja z GitHuba: wersje, wydania, pobieranie i skrypt podmiany."""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import updater


def release(tag, assets):
    return {"tag_name": tag, "assets": assets}


class VersionTests(unittest.TestCase):
    def test_version_key_reads_numbers(self):
        self.assertEqual(updater.version_key("v1.4.2"), [1, 4, 2])
        self.assertEqual(updater.version_key(""), [])

    def test_newer_release_is_detected(self):
        with mock.patch.object(updater, "APP_VERSION", "1.4.0"):
            self.assertTrue(updater.is_newer("1.4.1"))
            self.assertTrue(updater.is_newer("1.10.0"))
            self.assertTrue(updater.is_newer("2.0"))
            self.assertFalse(updater.is_newer("1.4.0"))
            self.assertFalse(updater.is_newer("1.3.9"))
            self.assertFalse(updater.is_newer(""))


class ParseReleaseTests(unittest.TestCase):
    def test_reads_version_and_exe(self):
        data = release("v1.5.0", [
            {"name": "BackupTool.exe", "browser_download_url": "https://x/exe"},
            {"name": "BackupTool.exe.sha256", "browser_download_url": "https://x/sha"},
        ])
        parsed = updater.parse_release(data)
        self.assertEqual(parsed, {"version": "1.5.0", "exe": "https://x/exe",
                                  "sha256": "https://x/sha"})

    def test_release_without_exe_is_ignored(self):
        self.assertIsNone(updater.parse_release(release("v1.5.0", [])))
        self.assertIsNone(updater.parse_release(release("", [])))
        self.assertIsNone(updater.parse_release(None))


class AvailableUpdateTests(unittest.TestCase):
    def test_older_release_is_not_an_update(self):
        with mock.patch.object(updater, "APP_VERSION", "1.4.0"), \
                mock.patch.object(updater, "fetch_latest_release",
                                  return_value={"version": "1.3.0", "exe": "x"}):
            self.assertIsNone(updater.available_update())

    def test_newer_release_is_returned(self):
        found = {"version": "1.5.0", "exe": "x"}
        with mock.patch.object(updater, "APP_VERSION", "1.4.0"), \
                mock.patch.object(updater, "fetch_latest_release", return_value=found):
            self.assertEqual(updater.available_update(), found)

    def test_network_error_is_not_an_update(self):
        with mock.patch.object(updater, "fetch_latest_release",
                               side_effect=OSError("offline")):
            self.assertIsNone(updater.available_update())


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self, size=-1):
        payload, self._payload = self._payload, b""
        return payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-update-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def test_downloads_and_checks_hash(self):
        dest = os.path.join(self.tmp, "BackupTool-1.5.0.exe")
        good = "a" * 64
        with mock.patch.object(updater.urllib.request, "urlopen",
                               side_effect=[FakeResponse(b"MZpayload"),
                                            FakeResponse(good.encode())]), \
                mock.patch.object(updater, "file_sha256", return_value=good):
            updater.download_release_asset("https://x/exe", dest, "https://x/sha")
        self.assertTrue(os.path.isfile(dest))

    def test_wrong_hash_is_rejected(self):
        dest = os.path.join(self.tmp, "bad.exe")
        with mock.patch.object(updater.urllib.request, "urlopen",
                               side_effect=[FakeResponse(b"MZpayload"),
                                            FakeResponse(("b" * 64).encode())]), \
                mock.patch.object(updater, "file_sha256", return_value="c" * 64):
            with self.assertRaises(updater.UpdaterError):
                updater.download_release_asset("https://x/exe", dest, "https://x/sha")
        self.assertFalse(os.path.exists(dest))

    def test_file_without_exe_header_is_rejected(self):
        dest = os.path.join(self.tmp, "fake.exe")
        with mock.patch.object(updater.urllib.request, "urlopen",
                               return_value=FakeResponse(b"<html>")):
            with self.assertRaises(updater.UpdaterError):
                updater.download_release_asset("https://x/exe", dest)


class SwapScriptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-swap-")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        patch = mock.patch.object(updater, "update_dir", lambda: self.tmp)
        patch.start()
        self.addCleanup(patch.stop)

    def test_script_waits_for_this_process_and_rolls_back(self):
        with mock.patch.object(updater.subprocess, "Popen") as popen:
            batch = updater.launch_self_update(os.path.join(self.tmp, "new.exe"), "1.5.0",
                                               target=os.path.join(self.tmp, "BackupTool.exe"))
        self.assertTrue(popen.called)
        with open(batch, "rb") as handle:
            text = handle.read().decode("utf-8")
        self.assertIn(f"Wait-Process -Id {os.getpid()}", text)
        self.assertIn("BackupTool.exe.old", text, "kopia do wycofania")
        self.assertIn("Contains('1.5.0 ')", text, "czeka na nową wersję w znaczniku")
        self.assertIn("\r\n", text, "batch potrzebuje CRLF")

    def test_marker_records_the_running_version(self):
        updater.write_start_marker()
        with open(updater.update_marker(), encoding="utf-8") as handle:
            self.assertTrue(handle.read().startswith(updater.APP_VERSION + " "))

    def test_failed_version_is_read_and_cleared(self):
        self.assertIsNone(updater.update_failed_version())
        with open(updater.update_failed_file(), "w", encoding="utf-8") as handle:
            handle.write("1.5.0")
        self.assertEqual(updater.update_failed_version(), "1.5.0")
        updater.clear_update_failed()
        self.assertIsNone(updater.update_failed_version())


if __name__ == "__main__":
    unittest.main()

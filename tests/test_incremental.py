#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mapa plików i przebudowa ZIP z poprzedniego archiwum (przyrost)."""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup_core as core
import cloud

def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path

class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-inc-")
        self.source = os.path.join(self.tmp, "src")
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(self.source)
        os.makedirs(self.out)
        write(os.path.join(self.source, "a.txt"), "AAA" * 400)
        write(os.path.join(self.source, "sub", "b.txt"), "BBB" * 400)
        write(os.path.join(self.source, "sub", "c.txt"), "CCC" * 400)
        self.root = os.path.join(self.tmp, "appdata")
        for patch in (mock.patch.object(core, "manifest_root",
                                        lambda: os.path.join(self.root, "manifests")),
                      mock.patch.object(core, "staging_root",
                                        lambda: os.path.join(self.root, "staging"))):
            patch.start()
            self.addCleanup(patch.stop)
        self.backup = core.new_backup("Kopia", [self.source], self.out, True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self):
        result = core.run_backup(self.backup)
        self.assertTrue(result["ok"], result["message"])
        return result["target"]

    def _names(self, target):
        with zipfile.ZipFile(target) as archive:
            return {n.replace("\\", "/") for n in archive.namelist()}

    def test_second_run_reuses_entries_without_recompressing(self):
        target = self._run()
        write(os.path.join(self.source, "a.txt"), "AAA v2" * 400)
        write(os.path.join(self.source, "nowy.txt"), "NOWY")
        os.remove(os.path.join(self.source, "sub", "c.txt"))
        compressed = []
        original = core._compress_file

        def spy(path, method):
            compressed.append(os.path.basename(path))
            return original(path, method)

        with mock.patch.object(core, "_compress_file", side_effect=spy), \
                mock.patch.object(core, "_write_zip") as full:
            self._run()

        self.assertFalse(full.called, "drugi przebieg nie może pakować od zera")
        names = self._names(target)
        self.assertIn("src/a.txt", names)
        self.assertIn("src/nowy.txt", names)
        self.assertNotIn("src/sub/c.txt", names)
        self.assertEqual(sorted(compressed), ["a.txt", "nowy.txt"],
                         "niezmienione pliki nie mogą być kompresowane ponownie")
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("src/a.txt").decode(), "AAA v2" * 400)
            self.assertEqual(archive.read("src/nowy.txt").decode(), "NOWY")

    def test_reused_entry_keeps_its_timestamp_and_compressed_bytes(self):
        target = self._run()
        with zipfile.ZipFile(target) as archive:
            before = {n: (i.date_time, i.CRC, i.compress_size)
                      for n, i in ((i.filename, i) for i in archive.infolist())}
        write(os.path.join(self.source, "nowy.txt"), "NOWY")
        self._run()
        with zipfile.ZipFile(target) as archive:
            after = {n: (i.date_time, i.CRC, i.compress_size)
                     for n, i in ((i.filename, i) for i in archive.infolist())}
        for name, values in before.items():
            self.assertEqual(after[name], values, f"wpis {name} został przepakowany")

    def test_nothing_changed_skips_rebuild_and_upload(self):
        target = self._run()
        before = os.path.getmtime(target)
        with mock.patch.object(core, "_incremental_zip") as incremental, \
                mock.patch.object(core, "_write_zip") as full, \
                mock.patch.object(cloud, "prepare_upload") as upload:
            result = core.run_backup(self.backup)
        self.assertTrue(result["ok"], result["message"])
        self.assertTrue(result.get("unchanged"))
        self.assertFalse(incremental.called)
        self.assertFalse(full.called)
        self.assertEqual(os.path.getmtime(target), before, "archiwum nie może być ruszane")

    def test_changed_file_sends_the_archive_again(self):
        self._run()
        write(os.path.join(self.source, "a.txt"), "AAA v5")
        result = core.run_backup(self.backup)
        self.assertTrue(result["ok"], result["message"])
        self.assertFalse(result.get("unchanged", False))

    def test_broken_base_archive_falls_back_to_full_rebuild(self):
        target = self._run()
        write(os.path.join(self.source, "a.txt"), "AAA v3")
        with open(target, "r+b") as handle:
            handle.seek(200)
            handle.write(b"\x00" * 64)
        full = mock.Mock(wraps=core._write_zip)
        with mock.patch.object(core, "_write_zip", full):
            self._run()
        self.assertTrue(full.called, "uszkodzona baza musi uruchomić pełny backup")
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("src/a.txt").decode(), "AAA v3")

    def test_missing_manifest_rebuilds_everything(self):
        self._run()
        os.remove(core.manifest_path(self.backup))
        write(os.path.join(self.source, "a.txt"), "AAA v4")
        full = mock.Mock(wraps=core._write_zip)
        with mock.patch.object(core, "_write_zip", full):
            self._run()
        self.assertTrue(full.called)
        self.assertEqual(len(core.load_manifest(self.backup, os.path.join(
            self.out, "Kopia.zip"))), 3)

    def test_manifest_is_bound_to_the_archive(self):
        target = self._run()
        manifest = core.load_manifest(self.backup, target)
        self.assertIsInstance(manifest, dict)
        self.assertEqual(len(manifest), 3)
        self.assertIsNone(core.load_manifest(self.backup, target + ".inny"))

    def test_manifest_lists_every_entry_after_two_runs(self):
        target = self._run()
        self._run()
        manifest = core.load_manifest(self.backup, target)
        names = {n.replace("\\", "/") for n in manifest}
        self.assertEqual(names, {"src/a.txt", "src/sub/b.txt", "src/sub/c.txt"})


class ZipWriterTest(unittest.TestCase):
    def test_writes_zip64_endings_above_65535_entries(self):
        tmp = tempfile.mkdtemp(prefix="bt-zip64-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "duzo.zip")
        count = 70_000
        with open(path, "wb") as handle:
            writer = core._ZipWriter(handle)
            for index in range(count):
                writer.add(f"dir/{index}.bin", (2026, 1, 2, 3, 4, 6), 0, 0, 0,
                           zipfile.ZIP_STORED, b"")
            writer.close()
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(len(archive.infolist()), count)
            info = archive.getinfo("dir/69999.bin")
            self.assertEqual(info.date_time, (2026, 1, 2, 3, 4, 6))

    def test_reads_back_compressed_payloads(self):
        tmp = tempfile.mkdtemp(prefix="bt-zipw-")
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "payload.zip")
        data = b"x" * 5000
        with open(path, "wb") as handle:
            writer = core._ZipWriter(handle)
            crc, payload, size = core._compress_data(data, zipfile.ZIP_DEFLATED)
            writer.add("a.txt", (2026, 5, 6, 7, 8, 10), crc, len(payload), size,
                       zipfile.ZIP_DEFLATED, payload)
            writer.close()
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("a.txt"), data)


class ScanProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-scan-")
        self.source = os.path.join(self.tmp, "src")
        for index in range(300):
            write(os.path.join(self.source, "d%d" % (index % 7), "f%d.txt" % index), "x")
        self.out = os.path.join(self.tmp, "out")
        os.makedirs(self.out)
        patch = mock.patch.object(core, "manifest_root",
                                  lambda: os.path.join(self.tmp, "manifests"))
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_collect_reports_growing_counts(self):
        seen = []
        entries = core.collect_spec_entries(core.manual_specs([self.source]),
                                            progress=seen.append)
        self.assertEqual(len(entries), 300)
        self.assertEqual(seen[-1], 300)
        self.assertEqual(seen, sorted(seen))

    def test_run_reports_scan_with_progress(self):
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        steps = []
        result = core.run_backup(
            backup, progress=lambda done, total, label: steps.append((done, total, label)))
        self.assertTrue(result["ok"], result["message"])
        scans = [(done, total) for done, total, label in steps if label == "scan"]
        self.assertTrue(scans, "skan musi raportować postęp")
        self.assertEqual(scans[-1][0], 300)

    def test_scan_progress_uses_the_previous_count_as_target(self):
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        self.assertTrue(core.run_backup(backup)["ok"])
        steps = []
        core.run_backup(backup, progress=lambda done, total, label:
                        steps.append((done, total, label)))
        scans = [(done, total) for done, total, label in steps if label == "scan"]
        self.assertEqual(scans[0][1], 300, "prognoza z mapy daje procenty")


if __name__ == "__main__":
    unittest.main()

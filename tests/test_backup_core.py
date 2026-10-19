#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy logiki BackupTool — bez GUI, bez zależności zewnętrznych.

Uruchomienie:  python -m unittest discover -s tests -v
"""

import json
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup_core as core
import i18n

i18n.set_language("pl")


def write(path: str, content: str = "x") -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


class ArchiveDetectionTests(unittest.TestCase):
    def test_single_extension_archives(self):
        for name in ["a.zip", "a.RAR", "a.7z", "a.tar", "a.gz", "a.iso"]:
            self.assertTrue(core.is_archive(name), name)

    def test_compound_extensions(self):
        self.assertTrue(core.is_archive("kopia.tar.gz"))
        self.assertTrue(core.is_archive("KOPIA.TAR.GZ"))
        self.assertTrue(core.is_archive("kopia.tar.bz2"))

    def test_plain_files_are_not_archives(self):
        for name in ["notatki.txt", "zdjecie.jpg", "raport.docx", "bez_rozszerzenia"]:
            self.assertFalse(core.is_archive(name), name)

    def test_folder_is_not_archive(self):
        self.assertFalse(core.is_archive("C:/dane/folder.zip/"))

    def test_zip_available_only_when_something_to_pack(self):
        self.assertFalse(core.zip_available([]))
        self.assertFalse(core.zip_available(["D:/a.zip"]))
        self.assertFalse(core.zip_available(["D:/a.zip", "D:/b.rar"]))
        self.assertTrue(core.zip_available(["D:/a.zip", "D:/folder"]))
        self.assertTrue(core.zip_available(["D:/dokument.txt"]))


class NameTests(unittest.TestCase):
    def test_illegal_characters_are_replaced(self):
        self.assertEqual(core.sanitize_name('a/b\\c:d*e?f"g<h>i|j'), "a-b-c-d-e-f-g-h-i-j")

    def test_trailing_dots_and_spaces_removed(self):
        self.assertEqual(core.sanitize_name("  Kopia.  "), "Kopia")

    def test_empty_name_falls_back(self):
        self.assertEqual(core.sanitize_name("   "), "Backup")
        self.assertEqual(core.sanitize_name("???"), "---"), "same znaki nielegalne zostaja jako myslniki"

    def test_duplicate_name_ignores_case_and_spaces(self):
        state = {"backups": [{"id": "1", "name": "Zdjecia"}]}
        self.assertTrue(core.duplicate_name(state, " zdjecia "))
        self.assertFalse(core.duplicate_name(state, "zdjecia", exclude_id="1"))
        self.assertFalse(core.duplicate_name(state, "Inne"))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-state-")
        self.path = os.path.join(self.tmp, "backups.json")

    def test_roundtrip_keeps_backups(self):
        state = core.default_state()
        backup = core.new_backup("Zdjecia", [self.tmp], self.tmp, True)
        core.put_backup(state, backup)
        core.save_state(state, self.path)
        loaded = core.load_state(self.path)
        self.assertEqual(len(loaded["backups"]), 1)
        self.assertEqual(loaded["backups"][0]["name"], "Zdjecia")
        self.assertEqual(loaded["backups"][0]["sources"], [self.tmp])

    def test_missing_file_gives_empty_state(self):
        self.assertEqual(core.load_state(os.path.join(self.tmp, "nie-ma.json"))["backups"], [])

    def test_corrupt_file_gives_empty_state(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{to nie jest json")
        self.assertEqual(core.load_state(self.path)["backups"], [])

    def test_normalization_fills_missing_fields(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"backups": [{"name": "A", "sources": ["C:/x"], "destination": "D:/y"}]},
                      handle)
        backup = core.load_state(self.path)["backups"][0]
        self.assertTrue(backup["id"])
        self.assertTrue(backup["use_zip"])
        self.assertIsNone(backup["last_run"])

    def test_put_updates_existing_entry(self):
        state = core.default_state()
        backup = core.new_backup("A", [self.tmp], self.tmp)
        core.put_backup(state, backup)
        backup["name"] = "B"
        core.put_backup(state, backup)
        self.assertEqual(len(state["backups"]), 1)
        self.assertEqual(state["backups"][0]["name"], "B")

    def test_remove(self):
        state = core.default_state()
        backup = core.new_backup("A", [self.tmp], self.tmp)
        core.put_backup(state, backup)
        self.assertTrue(core.remove_backup(state, backup["id"]))
        self.assertFalse(core.remove_backup(state, backup["id"]))
        self.assertEqual(state["backups"], [])


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-val-")
        self.source = os.path.join(self.tmp, "src")
        os.makedirs(os.path.join(self.source, "podfolder"))
        write(os.path.join(self.source, "a.txt"))

    def backup(self, **overrides):
        data = core.new_backup("Test", [self.source], os.path.join(self.tmp, "out"), True)
        data.update(overrides)
        return data

    def test_valid_backup_has_no_error(self):
        self.assertIsNone(core.validate_backup(self.backup()))

    def test_empty_name(self):
        self.assertIn("nazw", core.validate_backup(self.backup(name="  ")))

    def test_duplicate_name(self):
        state = {"backups": [{"id": "other", "name": "Test"}]}
        self.assertIn("już istnieje", core.validate_backup(self.backup(), state))

    def test_no_sources(self):
        self.assertIn("źródło", core.validate_backup(self.backup(sources=[])))

    def test_missing_source(self):
        error = core.validate_backup(self.backup(sources=[os.path.join(self.tmp, "brak")]))
        self.assertIn("Nie znaleziono", error)

    def test_empty_destination(self):
        self.assertIn("miejsce zapisu", core.validate_backup(self.backup(destination="")))

    def test_destination_inside_source_is_rejected(self):
        inside = os.path.join(self.source, "kopie")
        error = core.validate_backup(self.backup(destination=inside))
        self.assertIn("w folderze źródłowym", error)

    def test_destination_equal_to_source_is_rejected(self):
        error = core.validate_backup(self.backup(destination=self.source))
        self.assertIn("w folderze źródłowym", error)

    def test_destination_being_a_file_is_rejected(self):
        path = write(os.path.join(self.tmp, "plik.txt"))
        error = core.validate_backup(self.backup(destination=path))
        self.assertIn("folderem", error)


class TargetPathTests(unittest.TestCase):
    def test_zip_target(self):
        backup = core.new_backup("Moje zdjecia", ["C:/x/folder"], "D:/out", True)
        self.assertEqual(core.target_path(backup), os.path.join("D:\\out", "Moje zdjecia.zip"))

    def test_folder_target(self):
        backup = core.new_backup("Moje zdjecia", ["C:/x/folder"], "D:/out", False)
        self.assertEqual(core.target_path(backup), os.path.join("D:\\out", "Moje zdjecia"))

    def test_archive_source_forces_copy_dir(self):
        backup = core.new_backup("Paczka", ["C:/x/a.zip"], "D:/out", True)
        self.assertEqual(core.target_path(backup), os.path.join("D:\\out", "Paczka"))


class BackupRunTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-run-")
        self.source = os.path.join(self.tmp, "src")
        write(os.path.join(self.source, "a.txt"), "AAA")
        write(os.path.join(self.source, "sub", "b.txt"), "BBB")
        self.out = os.path.join(self.tmp, "out")

    def test_copy_mode_copies_tree(self):
        backup = core.new_backup("Kopia", [self.source], self.out, False)
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        target = os.path.join(self.out, "Kopia")
        self.assertEqual(result["target"], target)
        with open(os.path.join(target, "src", "a.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "AAA")
        self.assertTrue(os.path.isfile(os.path.join(target, "src", "sub", "b.txt")))
        self.assertEqual(result["files"], 2)

    def test_copy_mode_overwrites_and_adds_without_deleting(self):
        backup = core.new_backup("Kopia", [self.source], self.out, False)
        self.assertTrue(core.run_backup(backup)["ok"])
        # zmiana treści + nowy plik w źródle + plik, którego źródło już nie ma
        write(os.path.join(self.source, "a.txt"), "AAA v2")
        write(os.path.join(self.source, "nowy.txt"), "NOWY")
        stale = write(os.path.join(self.out, "Kopia", "src", "stary.txt"), "STARY")
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        with open(os.path.join(self.out, "Kopia", "src", "a.txt"), encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "AAA v2")
        self.assertTrue(os.path.isfile(os.path.join(self.out, "Kopia", "src", "nowy.txt")))
        self.assertTrue(os.path.isfile(stale), "kopie w folderze nie są usuwane")

    def test_zip_mode_creates_archive_with_source_root(self):
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        target = os.path.join(self.out, "Kopia.zip")
        self.assertEqual(result["target"], target)
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
        self.assertIn("src/a.txt", [n.replace("\\", "/") for n in names])
        self.assertIn("src/sub/b.txt", [n.replace("\\", "/") for n in names])

    def test_zip_mode_keeps_archive_sources_uncompressed(self):
        package = os.path.join(self.tmp, "paczka.zip")
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("wewnatrz.txt", "x" * 5000)
        backup = core.new_backup("Mieszany", [self.source, package], self.out, True)
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        with zipfile.ZipFile(result["target"]) as archive:
            info = archive.getinfo("paczka.zip")
        self.assertEqual(info.compress_type, zipfile.ZIP_STORED)

    def test_zip_mode_rebuild_replaces_old_archive(self):
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        self.assertTrue(core.run_backup(backup)["ok"])
        os.remove(os.path.join(self.source, "a.txt"))
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        with zipfile.ZipFile(result["target"]) as archive:
            names = [n.replace("\\", "/") for n in archive.namelist()]
        self.assertNotIn("src/a.txt", names)
        self.assertIn("src/sub/b.txt", names)

    def test_no_part_file_left_behind(self):
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        core.run_backup(backup)
        leftovers = [n for n in os.listdir(self.out) if n.endswith(core.TMP_SUFFIX)]
        self.assertEqual(leftovers, [])

    def test_cancel_leaves_old_archive_and_no_part(self):
        for index in range(5):
            write(os.path.join(self.source, "duzy_%d.txt" % index), "x" * 1000)
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        self.assertTrue(core.run_backup(backup)["ok"])
        original_size = os.path.getsize(os.path.join(self.out, "Kopia.zip"))

        calls = {"n": 0}

        def cancel():
            calls["n"] += 1
            return calls["n"] > 2

        result = core.run_backup(backup, cancelled=cancel)
        self.assertTrue(result["cancelled"])
        self.assertFalse(result["ok"])
        self.assertEqual(os.path.getsize(os.path.join(self.out, "Kopia.zip")), original_size)
        self.assertEqual([n for n in os.listdir(self.out) if n.endswith(core.TMP_SUFFIX)], [])

    def test_missing_source_is_reported_not_raised(self):
        backup = core.new_backup("Kopia", [os.path.join(self.tmp, "brak")], self.out, True)
        result = core.run_backup(backup)
        self.assertFalse(result["ok"])
        self.assertIn("Nie znaleziono", result["message"])

    def test_destination_inside_source_is_refused(self):
        backup = core.new_backup("Kopia", [self.source], os.path.join(self.source, "out"), True)
        result = core.run_backup(backup)
        self.assertFalse(result["ok"])
        self.assertIn("w folderze źródłowym", result["message"])

    def test_progress_reports_total_and_reaches_end(self):
        seen = []
        backup = core.new_backup("Kopia", [self.source], self.out, False)
        result = core.run_backup(backup, progress=lambda done, total, label: seen.append((done, total)))
        self.assertTrue(result["ok"], result["message"])
        finals = [item for item in seen if item[1] == 2]
        self.assertTrue(finals)
        self.assertEqual(finals[-1], (2, 2))

    def test_name_with_illegal_chars_does_not_break_target(self):
        backup = core.new_backup("Moje/zdjecia:2024", [self.source], self.out, True)
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        self.assertEqual(os.path.basename(result["target"]), "Moje-zdjecia-2024.zip")

    def test_apply_result_stores_last_run(self):
        backup = core.new_backup("Kopia", [self.source], self.out, True)
        result = core.run_backup(backup)
        core.apply_result(backup, result)
        self.assertTrue(backup["last_run"]["ok"])
        self.assertEqual(backup["last_run"]["files"], 2)
        self.assertGreater(backup["last_run"]["bytes"], 0)


class DuplicateBasenameTests(unittest.TestCase):
    def test_two_folders_with_same_name_get_suffix(self):
        self.assertEqual(core._unique_top_names(["C:/a/zdjecia", "D:/b/zdjecia"]),
                         ["zdjecia", "zdjecia (2)"])

    def test_copy_mode_keeps_both_sources(self):
        tmp = tempfile.mkdtemp(prefix="bt-dup-")
        first = write(os.path.join(tmp, "one", "zdjecia", "a.txt"), "A")
        second = write(os.path.join(tmp, "two", "zdjecia", "b.txt"), "B")
        out = os.path.join(tmp, "out")
        backup = core.new_backup("Kopia", [os.path.dirname(first), os.path.dirname(second)],
                                 out, False)
        result = core.run_backup(backup)
        self.assertTrue(result["ok"], result["message"])
        self.assertTrue(os.path.isfile(os.path.join(out, "Kopia", "zdjecia", "a.txt")))
        self.assertTrue(os.path.isfile(os.path.join(out, "Kopia", "zdjecia (2)", "b.txt")))


class HumanFormatTests(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(core.human_size(0), "0 B")
        self.assertEqual(core.human_size(1024), "1,0 KB")
        self.assertEqual(core.human_size(5 * 1024 * 1024), "5,0 MB")

    def test_human_when(self):
        now = core.datetime.datetime.now().isoformat(timespec="seconds")
        self.assertTrue(core.human_when(now).startswith("dziś"))
        self.assertEqual(core.human_when(""), "—")
        self.assertEqual(core.human_when("nie-data"), "—")

    def test_age_days(self):
        now = core.datetime.datetime.now()
        self.assertEqual(core.age_days(now.isoformat(timespec="seconds")), 0)
        self.assertEqual(core.age_days((now - core.datetime.timedelta(days=13)).isoformat()), 13)
        self.assertEqual(core.age_days(""), None)
        self.assertEqual(core.age_days("nie-data"), None)


if __name__ == "__main__":
    unittest.main(verbosity=2)

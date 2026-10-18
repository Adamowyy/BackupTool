#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testy backupu danych aplikacji (Hermes / Obsidian) — bez GUI."""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import appdata_detect
import backup_core as core
import i18n

i18n.set_language("pl")


def write(path, content="x"):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return path


def make_db(path, rows=("a", "b")):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.executemany("INSERT INTO t VALUES (?)", [(row,) for row in rows])
    conn.commit()
    conn.close()
    return path


def build_hermes(root, provider="mnemosyne"):
    write(os.path.join(root, "config.yaml"),
          "memory:\n  provider: '%s'\nother: 1\n" % provider)
    write(os.path.join(root, "SOUL.md"), "soul")
    write(os.path.join(root, "sessions", "s1.jsonl"), '{"a":1}')
    make_db(os.path.join(root, "projects.db"))
    write(os.path.join(root, "skills", "tool", "SKILL.md"), "# skill")
    write(os.path.join(root, "skills", "__pycache__", "x.pyc"), "pyc")
    write(os.path.join(root, "cron", "jobs.json"), "{}")
    write(os.path.join(root, "plugins", "p", "index.js"), "js")
    write(os.path.join(root, "memories", "notatka.md"), "# pamięć")
    write(os.path.join(root, "shared", "nous_auth.json"), '{"token":"secret"}')
    make_db(os.path.join(root, "memory_store.db"))
    make_db(os.path.join(root, "mnemosyne", "data", "mnemosyne.db"), ("m1", "m2"))
    write(os.path.join(root, "mnemosyne", "data", "mnemosyne.db-wal"), "wal")
    write(os.path.join(root, "mnemosyne", "config.yaml"), "ep_limit: 50000\n")
    write(os.path.join(root, "mnemosyne", "backups", "old.db"), "old")
    write(os.path.join(root, ".env"), "SECRET=1")
    write(os.path.join(root, "auth.json"), '{"token":"secret"}')
    write(os.path.join(root, "cache", "blob.bin"), "cache")
    return root


def build_vault(path):
    write(os.path.join(path, ".obsidian", "app.json"), "{}")
    write(os.path.join(path, ".obsidian", "cache", "big.bin"), "cache")
    write(os.path.join(path, ".trash", "kopia.md"), "trash")
    write(os.path.join(path, "Notatki", "pierwsza.md"), "# pierwsza")
    write(os.path.join(path, "Projekty", "BackupTool.md"), "# bt")
    return path


class HermesDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-appdata-")
        self.root = os.path.join(self.tmp, "hermes")
        build_hermes(self.root)

    def test_inventory_detects_both_memory_modes(self):
        inventory = appdata_detect.hermes_inventory(self.root, include_user_dir=False)
        self.assertTrue(inventory["mnemosyne_available"])
        self.assertTrue(inventory["builtin_available"])
        self.assertEqual(inventory["preferred_memory"], "mnemosyne")

    def test_provider_builtin_is_preferred_when_configured(self):
        root = os.path.join(self.tmp, "hermes-builtin")
        build_hermes(root, provider="builtin")
        inventory = appdata_detect.hermes_inventory(root, include_user_dir=False)
        self.assertEqual(inventory["preferred_memory"], "builtin")

    def test_detect_hermes_skips_unrelated_dirs(self):
        empty = os.path.join(self.tmp, "pusty")
        os.makedirs(empty)
        found = appdata_detect.detect_hermes(candidates=[empty, self.root])
        self.assertIsNotNone(found)
        self.assertEqual(os.path.normcase(found["root"]), os.path.normcase(self.root))

    def test_detect_hermes_returns_none_without_data(self):
        empty = os.path.join(self.tmp, "nic")
        os.makedirs(empty)
        self.assertIsNone(appdata_detect.detect_hermes(candidates=[empty]))

    def test_hermes_specs_mnemosyne_mode(self):
        inventory = appdata_detect.hermes_inventory(self.root, include_user_dir=False)
        entries = core.collect_spec_entries(
            appdata_detect.hermes_specs(inventory, "mnemosyne"))
        arcnames = {name.replace("\\", "/") for _src, name, _size in entries}
        self.assertIn("Hermes/config.yaml", arcnames)
        self.assertIn("Hermes/projects.db", arcnames)
        self.assertIn("Hermes/skills/tool/SKILL.md", arcnames)
        self.assertNotIn("Hermes/sessions/s1.jsonl", arcnames)
        self.assertFalse(any("sessions" in name for name in arcnames))
        self.assertIn("Hermes/Mnemosyne/mnemosyne.db", arcnames)
        self.assertIn("Hermes/Mnemosyne/config.yaml", arcnames)
        self.assertNotIn("Hermes/memories/notatka.md", arcnames)
        self.assertNotIn("Hermes/.env", arcnames)
        self.assertNotIn("Hermes/auth.json", arcnames)
        self.assertFalse(any(".env" in name or "auth.json" in name for name in arcnames))
        self.assertFalse(any("nous_auth" in name for name in arcnames))
        self.assertFalse(any("__pycache__" in name for name in arcnames))
        self.assertFalse(any(name.endswith("-wal") for name in arcnames))
        self.assertFalse(any("backups" in name for name in arcnames))

    def test_hermes_specs_builtin_mode(self):
        inventory = appdata_detect.hermes_inventory(self.root, include_user_dir=False)
        entries = core.collect_spec_entries(
            appdata_detect.hermes_specs(inventory, "builtin"))
        arcnames = {name.replace("\\", "/") for _src, name, _size in entries}
        self.assertIn("Hermes/memories/notatka.md", arcnames)
        self.assertIn("Hermes/memory_store.db", arcnames)
        self.assertIn("Hermes/config.yaml", arcnames)
        self.assertFalse(any("Mnemosyne" in name for name in arcnames))


class ObsidianTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-vault-")
        self.vault = build_vault(os.path.join(self.tmp, "Moj Sejf"))

    def test_specs_skip_cache_and_trash(self):
        entries = core.collect_spec_entries(
            appdata_detect.obsidian_specs({"vaults": [self.vault]}))
        arcnames = {name.replace("\\", "/") for _src, name, _size in entries}
        self.assertIn("Obsidian/Moj Sejf/Notatki/pierwsza.md", arcnames)
        self.assertIn("Obsidian/Moj Sejf/.obsidian/app.json", arcnames)
        self.assertFalse(any("/cache/" in name or name.endswith("/cache") for name in arcnames))
        self.assertFalse(any(".trash" in name for name in arcnames))

    def test_vaults_from_obsidian_json(self):
        config = write(os.path.join(self.tmp, "obsidian.json"),
                       json.dumps({"vaults": {"id1": {"path": self.vault}}}))
        self.assertEqual(appdata_detect._read_obsidian_config(config), [self.vault])

    def test_broken_config_is_ignored(self):
        config = write(os.path.join(self.tmp, "obsidian.json"), "{zle")
        self.assertEqual(appdata_detect._read_obsidian_config(config), [])


class AppDataBackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bt-appbackup-")
        self.hermes = build_hermes(os.path.join(self.tmp, "hermes"))
        self.vault = build_vault(os.path.join(self.tmp, "sejf"))
        self.detection = {
            "hermes": appdata_detect.hermes_inventory(self.hermes, include_user_dir=False),
            "obsidian": {"vaults": [self.vault], "config": None},
        }
        self.out = os.path.join(self.tmp, "out")

    def backup(self, **app_data):
        data = {"hermes": True, "obsidian": True, "memory": "mnemosyne"}
        data.update(app_data)
        return core.new_backup("Dane", [], self.out, True, app_data=data)

    def test_appdata_only_backup_is_valid(self):
        self.assertIsNone(core.validate_backup(self.backup(), detection=self.detection))

    def test_zip_available_for_appdata(self):
        self.assertTrue(core.zip_available_for(self.backup()))

    def test_run_creates_zip_with_both_apps(self):
        result = core.run_backup(self.backup(), detection=self.detection)
        self.assertTrue(result["ok"], result["message"])
        with zipfile.ZipFile(result["target"]) as archive:
            names = {name.replace("\\", "/") for name in archive.namelist()}
        self.assertIn("Hermes/config.yaml", names)
        self.assertIn("Obsidian/sejf/Notatki/pierwsza.md", names)
        self.assertFalse(any("auth.json" in name for name in names))

    def test_hermes_only_builtin_memory(self):
        backup = self.backup(obsidian=False, memory="builtin")
        result = core.run_backup(backup, detection=self.detection)
        self.assertTrue(result["ok"], result["message"])
        with zipfile.ZipFile(result["target"]) as archive:
            names = {name.replace("\\", "/") for name in archive.namelist()}
        self.assertIn("Hermes/memories/notatka.md", names)
        self.assertFalse(any("Mnemosyne" in name for name in names))

    def test_manual_sources_and_appdata_together(self):
        extra = write(os.path.join(self.tmp, "dodatkowe", "plik.txt"), "x")
        backup = core.new_backup("Dane", [os.path.dirname(extra)], self.out, True,
                                 app_data={"hermes": True, "obsidian": False,
                                           "memory": "mnemosyne"})
        result = core.run_backup(backup, detection=self.detection)
        self.assertTrue(result["ok"], result["message"])
        with zipfile.ZipFile(result["target"]) as archive:
            names = {name.replace("\\", "/") for name in archive.namelist()}
        self.assertIn("Hermes/config.yaml", names)
        self.assertIn("dodatkowe/plik.txt", names)

    def test_destination_inside_vault_is_rejected(self):
        backup = self.backup(hermes=False, obsidian=True)
        backup["destination"] = self.vault
        error = core.validate_backup(backup, detection=self.detection)
        self.assertIn("nie może leżeć", error)

    def test_unavailable_memory_mode_is_reported(self):
        detection = {"hermes": dict(self.detection["hermes"]),
                     "obsidian": {"vaults": [], "config": None}}
        detection["hermes"]["mnemosyne_available"] = False
        error = core.validate_backup(self.backup(obsidian=False, memory="mnemosyne"),
                                     detection=detection)
        self.assertIn("Mnemosyne", error)

    def test_missing_hermes_blocks_backup(self):
        detection = {"hermes": None, "obsidian": {"vaults": [self.vault]}}
        error = core.validate_backup(self.backup(), detection=detection)
        self.assertIn("Hermesa", error)

    def test_no_vaults_blocks_obsidian(self):
        detection = {"hermes": self.detection["hermes"],
                     "obsidian": {"vaults": []}}
        error = core.validate_backup(self.backup(hermes=False, obsidian=True),
                                     detection=detection)
        self.assertIn("Obsidiana", error)

    def test_sqlite_is_snapshotted_not_copied_half_written(self):
        db = os.path.join(self.out, "..", "zywa.db")
        make_db(db, rows=("x", "y", "z"))
        holder = sqlite3.connect(db)          # baza otwarta, jak w działającym Hermesie
        holder.execute("INSERT INTO t VALUES ('w')")
        holder.commit()
        try:
            backup = core.new_backup("Baza", [db], self.out, True)
            result = core.run_backup(backup)
            self.assertTrue(result["ok"], result["message"])
            extract = os.path.join(self.tmp, "extract")
            with zipfile.ZipFile(result["target"]) as archive:
                archive.extractall(extract)
            copy = os.path.join(extract, "zywa.db")
            conn = sqlite3.connect(copy)
            try:
                rows = [row[0] for row in conn.execute("SELECT x FROM t ORDER BY x")]
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            finally:
                conn.close()
            self.assertEqual(rows, ["w", "x", "y", "z"])
        finally:
            holder.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)

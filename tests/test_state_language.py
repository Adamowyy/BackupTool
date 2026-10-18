import os
import tempfile
import unittest

import backup_core as core
import i18n


class LanguageStateTest(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "backups.json")

    def tearDown(self):
        if os.path.exists(self.path):
            os.remove(self.path)
        os.rmdir(self.folder)

    def test_language_survives_save_and_load(self):
        state = core.default_state()
        state["language"] = "pl"
        core.save_state(state, self.path)
        self.assertEqual(core.load_state(self.path)["language"], "pl")

    def test_unknown_language_is_ignored(self):
        state = core.default_state()
        state["language"] = "de"
        core.save_state(state, self.path)
        self.assertEqual(core.load_state(self.path)["language"], "")

    def test_state_without_language_stays_empty(self):
        core.save_state(core.default_state(), self.path)
        self.assertEqual(core.load_state(self.path)["language"], "")

    def test_language_does_not_drop_backups(self):
        state = core.default_state()
        state["language"] = "pl"
        backup = core.new_backup("Photos", ["C:\\Photos"], "C:\\Out", True)
        core.put_backup(state, backup)
        core.save_state(state, self.path)
        loaded = core.load_state(self.path)
        self.assertEqual(len(loaded["backups"]), 1)
        self.assertEqual(loaded["backups"][0]["name"], "Photos")
        self.assertEqual(loaded["language"], "pl")


if __name__ == "__main__":
    unittest.main()

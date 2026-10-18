import os
import shutil
import tempfile
import unittest

import appdata_detect


class ScriptsIncludedTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.root, "scripts", "__pycache__"))
        os.makedirs(os.path.join(self.root, "assets", "icons"))
        open(os.path.join(self.root, "config.yaml"), "w").close()
        open(os.path.join(self.root, "scripts", "watchdog.py"), "w").close()
        open(os.path.join(self.root, "scripts", "__pycache__", "x.pyc"), "w").close()

    def test_scripts_folder_is_part_of_hermes_backup(self):
        specs = appdata_detect.hermes_specs({"root": self.root, "mnemosyne_dirs": []},
                                            "builtin")
        include = specs[0]["include"]
        self.assertIn("scripts", include)
        self.assertIn("assets", include)
        self.assertIn("__pycache__", specs[0]["skip_names"])

    def test_scripts_absent_from_include_when_missing(self):
        shutil.rmtree(os.path.join(self.root, "scripts"))
        specs = appdata_detect.hermes_specs({"root": self.root, "mnemosyne_dirs": []},
                                            "builtin")
        self.assertNotIn("scripts", specs[0]["include"])


if __name__ == "__main__":
    unittest.main()

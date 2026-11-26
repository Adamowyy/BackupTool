"""Wspólne środowisko testów: nie dotykamy prawdziwych folderów użytkownika."""

import os
import tempfile

_sandbox = os.path.join(tempfile.gettempdir(), "BackupTool-tests")
os.makedirs(_sandbox, exist_ok=True)
os.environ["LOCALAPPDATA"] = _sandbox

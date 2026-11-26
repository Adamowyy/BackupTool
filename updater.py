#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aktualizacja BackupTool z GitHuba: sprawdzenie, pobranie i podmiana exe.

Windows nie pozwala nadpisać działającego pliku, więc podmianę robi mały
skrypt wsadowy, który czeka na koniec tego procesu, kopiuje nowy exe na
miejsce starego i uruchamia aplikację ponownie.
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

APP_NAME = "BackupTool"
APP_VERSION = "1.4.0"
APP_EXE_NAME = "BackupTool.exe"
RELEASES_API = "https://api.github.com/repos/Adamowyy/BackupTool/releases/latest"
USER_AGENT = f"{APP_NAME}/{APP_VERSION}"
NEWLINE_CRLF = chr(13) + chr(10)


class UpdaterError(Exception):
    """Aktualizacja nie doszła do skutku; tekst jest kluczem tłumaczenia."""


def version_key(name):
    return [int(x) for x in re.findall(r"\d+", str(name or ""))]


def is_newer(version) -> bool:
    """Czy `version` jest nowsza od uruchomionej wersji."""
    theirs, ours = version_key(version), version_key(APP_VERSION)
    if not theirs:
        return False
    size = max(len(theirs), len(ours))
    return (theirs + [0] * (size - len(theirs))) > (ours + [0] * (size - len(ours)))


def parse_release(data, exe_name=APP_EXE_NAME):
    """{"version", "exe", "sha256"} z odpowiedzi GitHuba albo None.

    Wydanie bez pliku exe (sam opis, draft) nie jest aktualizacją.
    """
    version = str((data or {}).get("tag_name") or "").strip().lstrip("vV")
    if not version_key(version):
        return None
    assets = {}
    for asset in (data or {}).get("assets") or []:
        name = str(asset.get("name") or "").strip().lower()
        url = asset.get("browser_download_url")
        if name and url:
            assets[name] = url
    exe = assets.get(exe_name.lower())
    if not exe:
        return None
    return {"version": version, "exe": exe,
            "sha256": assets.get(exe_name.lower() + ".sha256")}


def fetch_latest_release(timeout=15):
    request = urllib.request.Request(RELEASES_API, headers={
        "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return parse_release(json.loads(response.read().decode("utf-8")))


def available_update(timeout=15):
    """Nowe wydanie do zainstalowania albo None (brak sieci też daje None)."""
    try:
        release = fetch_latest_release(timeout=timeout)
    except (OSError, ValueError):
        return None
    if not release or not is_newer(release.get("version")):
        return None
    return release


def update_dir():
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return os.path.join(base, APP_NAME, "update")


def update_marker():
    return os.path.join(update_dir(), "started.txt")


def update_failed_file():
    return os.path.join(update_dir(), "failed.txt")


def write_start_marker():
    """Dowód, że build wstał - skrypt podmiany czeka na ten plik."""
    try:
        os.makedirs(update_dir(), exist_ok=True)
        with open(update_marker(), "w", encoding="utf-8") as handle:
            handle.write(f"{APP_VERSION} {datetime.datetime.now():%Y-%m-%dT%H:%M:%S}")
    except OSError:
        pass


def update_failed_version():
    try:
        with open(update_failed_file(), encoding="utf-8") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def clear_update_failed():
    try:
        os.remove(update_failed_file())
    except OSError:
        pass


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_text(url, timeout=30):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", "replace")


def download_release_asset(url, dest, sha256_url=None, timeout=120):
    """Pobiera plik wydania, sprawdza sumę i to, czy to naprawdę exe."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, \
                open(tmp, "wb") as handle:
            shutil.copyfileobj(response, handle)
        if sha256_url:
            expected = (_fetch_text(sha256_url).split() or [""])[0].strip().lower()
            if len(expected) == 64 and file_sha256(tmp) != expected:
                raise UpdaterError("The download is damaged.")
        with open(tmp, "rb") as handle:
            if handle.read(2) != b"MZ":
                raise UpdaterError("The download is damaged.")
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    return dest


def download_app_update(release):
    version = re.sub(r"[^0-9A-Za-z._-]", "", release.get("version") or "")
    if not version:
        raise UpdaterError("The download is damaged.")
    dest = os.path.join(update_dir(), f"{APP_NAME}-{version}.exe")
    return download_release_asset(release["exe"], dest, release.get("sha256"))


def app_frozen():
    return bool(getattr(sys, "frozen", False))


def app_exe_path():
    return os.path.abspath(sys.executable if app_frozen() else __file__)


SELF_UPDATE_SCRIPT = NEWLINE_CRLF.join([
    "@echo off",
    "setlocal",
    'set "TARGET={target}"',
    'set "NEW={new}"',
    'set "OLD={old}"',
    'set "MARKER={marker}"',
    'set "FAILED={failed}"',
    'set "_MEIPASS2="',
    'set "_PYI_APPLICATION_HOME_DIR="',
    'set "_PYI_PARENT_PROCESS_LEVEL="',
    'powershell -NoProfile -WindowStyle Hidden -Command "Wait-Process -Id {pid} '
    '-ErrorAction SilentlyContinue" 2>nul',
    "set /a tries=0",
    ":move",
    'copy /y "%TARGET%" "%OLD%" >nul 2>&1',
    'move /y "%NEW%" "%TARGET%" >nul 2>&1',
    "if not errorlevel 1 goto start",
    "set /a tries+=1",
    "if %tries% geq 15 exit /b 1",
    "ping -n 2 127.0.0.1 >nul",
    "goto move",
    ":start",
    'del /q "%MARKER%" >nul 2>&1',
    'start "" "%TARGET%"',
    'powershell -NoProfile -WindowStyle Hidden -Command "for($i=0;$i -lt 120;$i++)'
    "{{ Start-Sleep -Milliseconds 500; if(Test-Path '{marker}'){{ "
    "if((Get-Content -Raw '{marker}').Contains('{version} ')){{ exit 0 }} }} }}; exit 1\"",
    "if not errorlevel 1 goto done",
    'copy /y "%OLD%" "%TARGET%" >nul 2>&1',
    "echo {version}> \"%FAILED%\"",
    'start "" "%TARGET%"',
    ":done",
    "",
])


def launch_self_update(new_exe, version, target=None):
    """Uruchamia skrypt podmiany; wywołujący musi zaraz zakończyć proces."""
    target = os.path.abspath(target or app_exe_path())
    wanted = re.sub(r"[^0-9A-Za-z._-]", "", str(version)) or APP_VERSION
    script = SELF_UPDATE_SCRIPT.format(
        target=target, new=os.path.abspath(new_exe), pid=os.getpid(),
        old=target + ".old", marker=update_marker(), failed=update_failed_file(),
        version=wanted)
    os.makedirs(update_dir(), exist_ok=True)
    batch = os.path.join(update_dir(), "apply_update.bat")
    with open(batch, "w", encoding="utf-8", newline="") as handle:
        handle.write(script)
    # _MEIPASS2 z jednego exe wskazywałby na folder, który zaraz znika.
    env = {k: v for k, v in os.environ.items()
           if k != "_MEIPASS2" and not k.startswith("_PYI")}
    flags = 0
    if os.name == "nt":
        flags = 0x08000000 | 0x00000200      # CREATE_NO_WINDOW | NEW_PROCESS_GROUP
    subprocess.Popen(["cmd.exe", "/c", batch], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, env=env)
    return batch

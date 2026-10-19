#!/usr/bin/env python3
"""Chmury przez rclone: instalacja, logowanie w przeglądarce, wysyłka backupu."""

from __future__ import annotations

import configparser
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request

import i18n
import zipfile

APP_DIR_NAME = "BackupTool"
RCLONE_ZIP_URL = "https://downloads.rclone.org/rclone-current-windows-amd64.zip"
REMOTE_NAMES = {"dropbox": "dropbox", "gdrive": "gdrive"}
BACKENDS = {"dropbox": "dropbox", "gdrive": "drive"}
PROVIDER_LABELS = {"dropbox": "Dropbox", "gdrive": "Google Drive"}
RCLONE_MIN_SIZE = 5_000_000

class CloudError(Exception):
    """Błąd integracji z chmurą — komunikat dla użytkownika."""

_ACTIVE_PIDS: set = set()
_ACTIVE_LOCK = threading.Lock()

def kill_active() -> None:
    """Ubija trwające wysyłki rclone (wywoływane przy zamykaniu aplikacji)."""
    with _ACTIVE_LOCK:
        pids = list(_ACTIVE_PIDS)
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, timeout=10, **_hidden_kwargs())
        except Exception:
            pass
    with _ACTIVE_LOCK:
        _ACTIVE_PIDS.clear()

def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME)

def cache_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME, "rclone")

def conf_path() -> str:
    override = os.environ.get("BACKUPTOOL_RCLONE_CONF")
    return override or os.path.join(data_dir(), "rclone.conf")

def rclone_exe() -> str | None:
    candidates = [os.path.join(cache_dir(), "rclone.exe")]
    for path in candidates:
        if os.path.isfile(path) and os.path.getsize(path) > RCLONE_MIN_SIZE:
            return path
    return None

def _download(url: str, target: str, timeout: int = 120) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "BackupTool"})
    with urllib.request.urlopen(request, timeout=timeout) as response, \
            open(target, "wb") as handle:
        shutil.copyfileobj(response, handle)

def install_rclone(progress=None) -> str:
    """Pobiera rclone.exe do %LOCALAPPDATA%\\BackupTool\\rclone (raz)."""
    existing = rclone_exe()
    if existing:
        return existing

    folder = cache_dir()
    os.makedirs(folder, exist_ok=True)
    archive = os.path.join(folder, "rclone.zip")
    if progress:
        progress(i18n.t("Downloading rclone (~32 MB)…"))

    try:
        _download(RCLONE_ZIP_URL, archive)
    except Exception as exc:  # noqa: BLE001 - sieć bywa różna
        raise CloudError(i18n.t("Could not download rclone: {error}", error=exc)) from exc

    try:
        with zipfile.ZipFile(archive) as bundle:
            names = [n for n in bundle.namelist() if n.lower().endswith("rclone.exe")]
            if not names:
                raise CloudError(i18n.t("The rclone package has no rclone.exe."))
            if progress:
                progress(i18n.t("Unpacking rclone…"))
            with bundle.open(names[0]) as source, \
                    open(os.path.join(folder, "rclone.exe"), "wb") as target:
                shutil.copyfileobj(source, target)
    except zipfile.BadZipFile as exc:
        raise CloudError(i18n.t("The downloaded rclone archive is damaged.")) from exc
    finally:
        _silent_remove(archive)

    exe = os.path.join(folder, "rclone.exe")
    if not os.path.isfile(exe):
        raise CloudError(i18n.t("Could not install rclone."))
    version = rclone_version(exe)
    if not version:
        _silent_remove(exe)
        raise CloudError(i18n.t("rclone did not start after unpacking."))
    return exe

def _hidden_kwargs() -> dict:
    """Brak mrugającego okna konsoli przy każdym uruchomieniu rclone."""
    if os.name != "nt":
        return {}
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": info}

def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass

def _remove_partials(local_file: str) -> None:
    """rclone pisze `<nazwa>.<hash>.partial`; po ubitym procesie zostaje taki trup.

    Bez tego każde przerwane pobranie zostawia na dysku plik wielkości tego, co
    zdążyło zlecieć, a użytkownik myśli, że kopia jest kompletna.
    """
    folder = os.path.dirname(local_file) or "."
    prefix = os.path.basename(local_file) + "."
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for name in names:
        if name.startswith(prefix) and name.endswith(".partial"):
            _silent_remove(os.path.join(folder, name))

def rclone_version(exe: str | None = None) -> str:
    exe = exe or rclone_exe()
    if not exe:
        return ""
    try:
        result = subprocess.run([exe, "version"], capture_output=True, text=True,
                                timeout=30, encoding="utf-8", errors="replace",
                                **_hidden_kwargs())
    except (OSError, subprocess.SubprocessError):
        return ""
    first = (result.stdout or "").splitlines()
    match = re.search(r"v\d+\.\d+\.\d+", first[0] if first else "")
    return match.group(0) if match else ""

def _read_conf() -> configparser.ConfigParser:
    parser = configparser.ConfigParser()
    path = conf_path()
    if os.path.isfile(path):
        try:
            parser.read(path, encoding="utf-8")
        except configparser.Error:
            return configparser.ConfigParser()
    return parser

def _write_conf(parser: configparser.ConfigParser) -> None:
    path = conf_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buffer = io.StringIO()
    parser.write(buffer)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        handle.write(buffer.getvalue())
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass

def remote_ready(provider: str) -> bool:
    """Czy konto jest już zalogowane (jest sekcja z tokenem)."""
    parser = _read_conf()
    name = REMOTE_NAMES.get(provider)
    if not name or not parser.has_section(name):
        return False
    token = parser.get(name, "token", fallback="")
    return "refresh_token" in token or "access_token" in token

def remote_account(provider: str) -> str:
    """Login/e-mail zapisany przez rclone, jeśli jest (do podglądu w UI)."""
    parser = _read_conf()
    name = REMOTE_NAMES.get(provider)
    if not name or not parser.has_section(name):
        return ""
    for key in ("user", "email", "account"):
        value = parser.get(name, key, fallback="")
        if value:
            return value
    return ""

def authorize(provider: str, client_id: str = "", client_secret: str = "",
              timeout: int = 300, on_status=None) -> None:
    """Logowanie w przeglądarce; zapisuje token do rclone.conf."""
    if provider not in BACKENDS:
        raise CloudError(i18n.t("Unknown provider: {provider}", provider=provider))
    exe = install_rclone(on_status)
    if provider == "gdrive" and not client_id.strip():
        raise CloudError(i18n.t("Google Drive needs your own client ID (see README)."))

    args = [exe, "authorize", BACKENDS[provider]]
    if provider == "gdrive":
        args += [client_id.strip(), client_secret.strip()]
    if on_status:
        on_status(i18n.t("Opening the browser — sign in and approve access…"))

    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                                encoding="utf-8", errors="replace", **_hidden_kwargs())
    except subprocess.TimeoutExpired as exc:
        raise CloudError(i18n.t("Sign-in was not finished (timeout).")) from exc
    except OSError as exc:
        raise CloudError(f"Nie udało się uruchomić rclone: {exc}") from exc

    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip().splitlines()
        raise CloudError(message[-1] if message else "Logowanie odrzucone.")

    token = _extract_token(result.stdout or "")
    if not token:
        raise CloudError(i18n.t("rclone did not return a token."))

    parser = _read_conf()
    name = REMOTE_NAMES[provider]
    if not parser.has_section(name):
        parser.add_section(name)
    parser.set(name, "type", BACKENDS[provider])
    parser.set(name, "token", json.dumps(token))
    if provider == "gdrive":
        parser.set(name, "scope", "drive")
        parser.set(name, "client_id", client_id.strip())
        parser.set(name, "client_secret", client_secret.strip())
    _write_conf(parser)

def _extract_token(output: str) -> dict | None:
    start = output.find('{"access_token"')
    if start < 0:
        start = output.find("{")
    while start >= 0:
        try:
            token, _end = json.JSONDecoder().raw_decode(output[start:])
        except ValueError:
            start = output.find("{", start + 1)
            continue
        if isinstance(token, dict) and token.get("access_token"):
            return token
        start = output.find("{", start + 1)
    return None

def forget(provider: str) -> None:
    """Odlacza konto (usuwa sekcję z rclone.conf)."""
    parser = _read_conf()
    name = REMOTE_NAMES.get(provider, "")
    if name and parser.has_section(name):
        parser.remove_section(name)
        _write_conf(parser)

def test_remote(provider: str, timeout: int = 60) -> tuple:
    """Sprawdza, czy token nadal działa (`rclone about`)."""
    exe = rclone_exe()
    name = REMOTE_NAMES.get(provider, "")
    if not exe or not name:
        return False, "rclone nie jest zainstalowany"
    try:
        result = subprocess.run(
            [exe, "about", f"{name}:", "--json"], capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
            env=_env(), **_hidden_kwargs())
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    if result.returncode == 0:
        return True, "konto działa"
    return False, _first_error(result)

def _env() -> dict:
    env = dict(os.environ)
    env["RCLONE_CONFIG"] = conf_path()
    env["RCLONE_ASK_PASSWORD"] = "false"
    return env

def _percent_from_json(line: str):
    """Procent z linii statystyk rclone (bytes/totalBytes, potem pliki)."""
    try:
        payload = json.loads(line)
    except ValueError:
        return None
    stats = payload.get("stats") if isinstance(payload, dict) else None
    if not isinstance(stats, dict):
        return None
    total_bytes = stats.get("totalBytes") or 0
    if total_bytes:
        return int(min(100, (stats.get("bytes") or 0) * 100 / total_bytes))
    total_files = stats.get("totalTransfers") or 0
    if total_files:
        return int(min(100, (stats.get("transfers") or 0) * 100 / total_files))
    return None

def _error_from_lines(lines) -> str:
    important = []
    for line in lines:
        for marker in ("Fatal error:", "CRITICAL:", "ERROR :", "NOTICE: Failed"):
            if marker in line:
                important.append(line.split(marker, 1)[-1].strip())
                break
    if important:
        return important[-1][:300]
    return (lines[-1][:300] if lines else "nieznany błąd rclone")

def _first_error(result) -> str:
    lines = [line.strip() for line in (result.stderr or result.stdout or "").splitlines()
             if line.strip()]
    important = []
    for line in lines:
        for marker in ("Fatal error:", "CRITICAL:", "ERROR :", "NOTICE: Failed"):
            if marker in line:
                important.append(line.split(marker, 1)[-1].strip())
                break
    if important:
        return important[-1][:300]
    for line in reversed(lines):
        if not re.match(r"^\d{4}/\d{2}/\d{2}", line) and "Use \"rclone" not in line:
            return line[:300]
    return i18n.t("Unknown rclone error")

def _remote_ref(provider: str, remote_dir: str, filename: str) -> str:
    """Pełna referencja rclone do jednego pliku w chmurze (`dropbox:Backups/x.zip`)."""
    name = REMOTE_NAMES.get(provider, "")
    folder = (remote_dir or "").replace("\\", "/").strip("/ ")
    return f"{name}:{folder}/{filename}" if folder else f"{name}:{filename}"

def remote_file(provider: str, remote_dir: str, filename: str,
                timeout: int = 120) -> dict | None:
    """Czy kopia jest w chmurze? Zwraca {name, size, modified} albo None.

    Jeden `rclone lsjson --stat` (ok. 2 s na Google Drive) — nie pobiera nic,
    więc nadaje się na sprawdzenie tuż przed kliknięciem „Pobierz”.
    """
    exe = rclone_exe()
    if not exe:
        raise CloudError(i18n.t("Rclone is not installed."))
    if not REMOTE_NAMES.get(provider):
        raise CloudError(i18n.t("Unknown provider: {provider}", provider=provider))
    if not remote_ready(provider):
        raise CloudError(i18n.t("Account disconnected — connect it again."))

    ref = _remote_ref(provider, remote_dir, filename)
    try:
        result = subprocess.run([exe, "lsjson", ref, "--stat"], capture_output=True,
                                text=True, timeout=timeout, encoding="utf-8",
                                errors="replace", env=_env(), **_hidden_kwargs())
    except subprocess.TimeoutExpired as exc:
        raise CloudError(i18n.t("The cloud did not answer in time.")) from exc
    except OSError as exc:
        raise CloudError(i18n.t("Could not start rclone: {error}", error=exc)) from exc

    if result.returncode != 0:
        message = _first_error(result)
        lowered = message.lower()
        if "not found" in lowered or "doesn't exist" in lowered or "not exist" in lowered:
            return None
        if "invalid_grant" in message or "invalid token" in lowered:
            raise CloudError(i18n.t("Account disconnected — connect it again."))
        raise CloudError(i18n.t("Cloud check failed: {message}", message=message))

    try:
        payload = json.loads(result.stdout or "{}")
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("IsDir"):
        return None
    return {"name": payload.get("Name") or filename,
            "size": int(payload.get("Size") or 0),
            "modified": payload.get("ModTime") or ""}

def download_file(local_file: str, provider: str, remote_dir: str, filename: str,
                  on_percent=None, should_stop=None) -> None:
    """Pobiera jedną kopię z chmury na dysk (rclone `copyto`)."""
    exe = rclone_exe()
    if not exe:
        raise CloudError(i18n.t("Rclone is not installed."))
    if not REMOTE_NAMES.get(provider):
        raise CloudError(i18n.t("Unknown provider: {provider}", provider=provider))
    ref = _remote_ref(provider, remote_dir, filename)
    folder = os.path.dirname(local_file)
    if folder:
        os.makedirs(folder, exist_ok=True)
    try:
        _run_rclone([exe, "copyto", ref, local_file, "--transfers", "1"], on_percent,
                    should_stop, action="download")
    except CloudError:
        _remove_partials(local_file)
        raise
    _remove_partials(local_file)
    if not os.path.isfile(local_file):
        raise CloudError(i18n.t("The download finished but the file is missing."))

def upload_file(local_file: str, provider: str, remote_dir: str,
                on_status=None, on_percent=None, should_stop=None) -> None:
    """Wysyła pojedynczy plik (ZIP) do chmury, raportując procent."""
    exe = rclone_exe()
    name = REMOTE_NAMES.get(provider, "")
    if not exe or not name:
        raise CloudError(i18n.t("Rclone is not installed."))
    remote_dir = remote_dir.strip("/ ")
    filename = os.path.basename(local_file)
    target = f"{name}:{remote_dir}/{filename}" if remote_dir else f"{name}:{filename}"
    if on_status:
        on_status(f"Wysyłam {filename} do {PROVIDER_LABELS.get(provider, provider)}…")
    _run_rclone([exe, "copyto", local_file, target, "--transfers", "1",
                 "--drive-chunk-size", "32M"], on_percent, should_stop)

def upload_dir(local_dir: str, provider: str, remote_dir: str,
               on_status=None, on_percent=None, should_stop=None) -> None:
    """Wysyła folder backupu; rclone pomija pliki bez zmian."""
    exe = rclone_exe()
    name = REMOTE_NAMES.get(provider, "")
    if not exe or not name:
        raise CloudError("Brak zainstalowanego rclone.")
    remote_dir = remote_dir.strip("/ ")
    if on_status:
        on_status(f"Wysyłam pliki do {PROVIDER_LABELS.get(provider, provider)}…")
    destination = f"{name}:{remote_dir}" if remote_dir else f"{name}:"
    _run_rclone([exe, "copy", local_dir, destination,
                 "--transfers", "8", "--checkers", "8", "--fast-list",
                 "--no-update-dir-modtime"], on_percent, should_stop)

_PERCENT = re.compile(r"(\d{1,3})%")
_STATS = ("--stats", "1s", "--log-level", "INFO", "--use-json-log")

def _run_rclone(args: list, on_percent=None, should_stop=None,
                action: str = "upload") -> None:
    command = list(args) + list(_STATS) + ["--config", conf_path()]
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace", env=_env(), **_hidden_kwargs())
    except OSError as exc:
        raise CloudError(f"Nie udało się uruchomić rclone: {exc}") from exc

    with _ACTIVE_LOCK:
        _ACTIVE_PIDS.add(process.pid)
    tail = []
    last_percent = -1
    assert process.stdout is not None
    for line in process.stdout:
        line = line.rstrip()
        if should_stop is not None and should_stop():
            try:
                process.kill()
            except OSError:
                pass
            with _ACTIVE_LOCK:
                _ACTIVE_PIDS.discard(process.pid)
            raise CloudError(i18n.t("Upload cancelled — the copy stays local only.")
                             if action == "upload"
                             else i18n.t("Download cancelled."))
        if line:
            tail.append(line)
            if len(tail) > 40:
                del tail[0]
        if on_percent and line.startswith("{"):
            percent = _percent_from_json(line)
            if percent is not None and percent != last_percent:
                last_percent = percent
                on_percent(percent)
    try:
        code = process.wait(timeout=1800)
    except subprocess.TimeoutExpired as exc:
        process.kill()
        raise CloudError(i18n.t("Upload took too long and was aborted.")
                         if action == "upload"
                         else i18n.t("The download took too long and was aborted.")) from exc
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE_PIDS.discard(process.pid)

    if code != 0:
        message = _error_from_lines(tail)
        if "invalid_grant" in message or "invalid token" in message.lower():
            raise CloudError(i18n.t("Account disconnected — connect it again."))
        if "invalid_client" in message:
            raise CloudError(i18n.t("Wrong client ID / secret (see the Google guide)."))
        raise CloudError(i18n.t("Cloud rejected the upload: {message}", message=message)
                         if action == "upload"
                         else i18n.t("Cloud rejected the download: {message}",
                                     message=message))

def prepare_upload(backup: dict, local_target: str, on_status=None,
                   on_percent=None, should_stop=None) -> bool:
    """Wysyła gotowy backup do wybranej chmury. True = nic nie robiono."""
    cloud = backup.get("cloud") or {}
    provider = cloud.get("provider", "none")
    if provider in ("", "none", None):
        return True
    if not remote_ready(provider):
        raise CloudError("Konto chmury nie jest połączone — wejdź w ustawienia backupu.")
    remote_dir = (cloud.get("path") or "").strip()
    remote_dir = remote_dir.replace("\\", "/")
    if os.path.isdir(local_target):
        parent = f"{remote_dir}/{os.path.basename(local_target)}" if remote_dir             else os.path.basename(local_target)
        upload_dir(local_target, provider, parent, on_status, on_percent, should_stop)
    else:
        upload_file(local_target, provider, remote_dir, on_status, on_percent, should_stop)
    return False
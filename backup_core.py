#!/usr/bin/env python3
"""BackupTool — logika: stan aplikacji, wykrywanie archiwów, kopiowanie i ZIP."""

from __future__ import annotations

import contextlib
import datetime
import gzip
import json
import os
import re
import shutil
import sqlite3
import struct
import tempfile
import time
import uuid
import zipfile
import zlib

import appdata_detect
import cloud
import i18n

APP_DIR_NAME = "BackupTool"
STATE_FILENAME = "backups.json"
STATE_VERSION = 1
TMP_SUFFIX = ".part"

MEMORY_MODES = ("mnemosyne", "builtin")
CLOUD_PROVIDERS = ("none", "dropbox", "gdrive")
APP_DATA_DEFAULT = {"hermes": False, "obsidian": False, "memory": "builtin"}

ARCHIVE_EXTS = {
    ".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz", ".tbz2",
    ".xz", ".txz", ".zst", ".lz", ".lzma", ".cab", ".arj", ".iso",
}
_COMPOUND_EXTS = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".tar.lz")

_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

class BackupError(Exception):
    """Błąd, który użytkownik powinien zobaczyć jako komunikat."""

class Cancelled(BackupError):
    """Użytkownik przerwał kopiowanie."""

def now_iso() -> str:
    """Znacznik czasu w formacie ISO (bez strefy, wystarcza lokalnie)."""
    return datetime.datetime.now().isoformat(timespec="seconds")

def is_archive(path: str) -> bool:
    """Czy plik jest już paczką (.zip, .rar, .7z, .tar.gz, ...)."""
    if not path:
        return False
    name = os.path.basename(path).lower()
    for ext in _COMPOUND_EXTS:
        if name.endswith(ext):
            return True
    return os.path.splitext(name)[1] in ARCHIVE_EXTS

def source_kind(path: str) -> str:
    """"folder" albo "file" — do wyświetlania w liście źródeł."""
    return "folder" if path and os.path.isdir(path) else "file"

def zip_available(sources) -> bool:
    """Czy dla tych źródeł można włączyć pakowanie do ZIP."""
    return any(s and not is_archive(s) for s in (sources or []))

def normalize_app_data(raw) -> dict:
    """Ustawienia danych aplikacji (Hermes / Obsidian + tryb pamięci)."""
    data = dict(APP_DATA_DEFAULT)
    if isinstance(raw, dict):
        data["hermes"] = bool(raw.get("hermes"))
        data["obsidian"] = bool(raw.get("obsidian"))
        memory = raw.get("memory")
        if memory in MEMORY_MODES:
            data["memory"] = memory
    return data

def app_data_enabled(backup: dict) -> bool:
    data = normalize_app_data(backup.get("app_data"))
    return bool(data["hermes"] or data["obsidian"])

def memory_mode(backup: dict) -> str:
    return normalize_app_data(backup.get("app_data"))["memory"]

def zip_available_for(backup: dict) -> bool:
    """ZIP dla całego backupu — dane aplikacji to zawsze pliki, nie paczki."""
    if app_data_enabled(backup):
        return True
    return zip_available(backup.get("sources") or [])

def normalize_cloud(raw) -> dict:
    """Cel zapisu plus folder zapamiętany osobno dla każdej chmury.

    Przełączanie Lokalnie / Dropbox / Google Drive nie kasuje wpisanych folderów,
    więc powrót do chmury odtwarza to, co było tam ustawione.
    """
    data = {"provider": "none", "path": "", "paths": {}}
    if not isinstance(raw, dict):
        return data

    provider = str(raw.get("provider") or "none").lower()
    if provider in ("", "local"):
        provider = "none"
    if provider not in CLOUD_PROVIDERS:
        provider = "none"

    paths = {}
    stored = raw.get("paths")
    if isinstance(stored, dict):
        for name, value in stored.items():
            key = str(name).lower()
            if key in CLOUD_PROVIDERS and key != "none" and isinstance(value, str):
                paths[key] = value.strip(" /\\")

    path = str(raw.get("path") or "").strip(" /\\")
    if provider != "none" and ("path" in raw or provider not in paths):
        # Jawne „path” wygrywa, więc wyczyszczone pole nie odrasta ze starej wartości.
        paths[provider] = path

    data["provider"] = provider
    data["path"] = paths.get(provider, "") if provider != "none" else ""
    data["paths"] = paths
    return data

def cloud_path_for(backup: dict, provider: str) -> str:
    """Folder zapamiętany dla wskazanej chmury (nawet gdy aktywna jest inna)."""
    return normalize_cloud(backup.get("cloud"))["paths"].get(provider, "")

def switch_cloud(raw, provider: str) -> dict:
    """Zmiana trybu (Lokalnie / Dropbox / Google Drive) z pamięcią folderów.

    Bieżący folder trafia do mapy pod swoją chmurę, a nowa chmura dostaje ten,
    który miała zapisany wcześniej, więc przełączanie niczego nie kasuje.
    """
    data = normalize_cloud(raw)
    if provider not in CLOUD_PROVIDERS:
        provider = "none"
    if data["provider"] != "none":
        data["paths"][data["provider"]] = data["path"]
    data["provider"] = provider
    data["path"] = data["paths"].get(provider, "") if provider != "none" else ""
    return data


def cloud_provider(backup: dict) -> str:
    return normalize_cloud(backup.get("cloud"))["provider"]

def cloud_remote_dir(backup: dict) -> str:
    """Folder w chmurze; domyślnie BackupTool/<nazwa>."""
    path = (normalize_cloud(backup.get("cloud"))["path"] or "").strip()
    return path.replace("\\", "/").strip("/")

def staging_root() -> str:
    """Tymczasowy folder na kopię, zanim poleci do chmury."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME, "staging")

def staging_path(backup: dict) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(backup.get("id") or "backup"))[:32]
    return os.path.join(staging_root(), safe_id)

MANIFEST_VERSION = 1

def manifest_root() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME, "manifests")

def manifest_path(backup: dict) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", str(backup.get("id") or "backup"))[:32]
    return os.path.join(manifest_root(), safe_id + ".json.gz")

def _cache_size(path) -> int:
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def cache_usage() -> int:
    """Ile miejsca zajmują mapy i staging (bajty)."""
    return _cache_size(staging_root()) + _cache_size(manifest_root())


def purge_stale(keep_ids, older_than_days=0, include_active=False) -> tuple:
    """Mapy i staging po backupach spoza listy. Zwraca (usunięte wpisy, bajty)."""
    keep = set() if include_active else {
        re.sub(r"[^A-Za-z0-9_.-]", "_", str(item or ""))[:32] for item in keep_ids}
    cutoff = time.time() - older_than_days * 86400
    removed = 0
    freed = 0
    for root, suffix, is_dir in ((staging_root(), "", True),
                                 (manifest_root(), ".json.gz", False)):
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for name in names:
            if suffix:
                if not name.endswith(suffix):
                    continue
                entry = name[:-len(suffix)]
            else:
                entry = name
            if not entry or entry in keep:
                continue
            if not re.fullmatch(r"[0-9A-Za-z_-]{1,64}", entry):
                continue
            path = os.path.join(root, name)
            try:
                if older_than_days and os.path.getmtime(path) > cutoff:
                    continue
                freed += _cache_size(path)
                if is_dir:
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
                removed += 1
            except OSError:
                pass
    return removed, freed


def load_manifest(backup: dict, archive: str):
    """Mapa plików z poprzedniego przebiegu; None, gdy nie pasuje do archiwum."""
    try:
        with gzip.open(manifest_path(backup), "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
        return None
    entries = payload.get("entries")
    if not isinstance(entries, dict) or not entries:
        return None
    try:
        if int(payload.get("archive_size") or -1) != os.path.getsize(archive):
            return None
    except (OSError, TypeError, ValueError):
        return None
    return entries

def save_manifest(backup: dict, archive: str, entries: dict) -> None:
    if not entries:
        return
    try:
        os.makedirs(manifest_root(), exist_ok=True)
        payload = {"version": MANIFEST_VERSION,
                   "archive_size": os.path.getsize(archive), "entries": entries}
    except OSError:
        return
    path = manifest_path(backup)
    tmp = path + TMP_SUFFIX
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except OSError:
        _silent_remove(tmp)

def _cleanup_parts(folder: str) -> None:
    """Same niedokończone pliki; gotowe archiwum zostaje jako baza dla przyrostu."""
    try:
        for name in os.listdir(folder):
            if name.endswith(TMP_SUFFIX):
                _silent_remove(os.path.join(folder, name))
    except OSError:
        pass

def use_zip_for(backup: dict) -> bool:
    """Chmura zawsze dostaje jeden plik ZIP — folder to tysiące zapytań i limity API."""
    if cloud_provider(backup) != "none":
        return True
    return bool(backup.get("use_zip")) and zip_available_for(backup)

def display_target(backup: dict) -> str:
    """Czytelny cel zapisu: ścieżka lokalna albo Dropbox: BackupTool/nazwa.zip."""
    provider = cloud_provider(backup)
    if provider == "none":
        return target_path(backup)
    label = cloud.PROVIDER_LABELS.get(provider, provider)
    leaf = os.path.basename(target_path(backup))
    folder = cloud_remote_dir(backup)
    return f"{label}  →  {folder}/{leaf}" if folder else f"{label}  →  {leaf}"

def sanitize_name(name: str) -> str:
    """Nazwa backupu przerobiona na poprawną nazwę pliku/folderu."""
    cleaned = _ILLEGAL_CHARS.sub("-", (name or "").strip())
    cleaned = cleaned.strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Backup"

def human_size(num) -> str:
    """48,2 MB — z przecinkiem, po polsku."""
    if num is None:
        return "—"
    value = float(num)
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    if index == 0:
        return f"{int(value)} B"
    text = f"{value:.1f}"
    if i18n.language() == "pl":
        text = text.replace(".", ",")
    return text + " " + units[index]

def age_days(iso: str):
    """Ile dni kalendarzowych minęło od ISO albo None, gdy data jest zła."""
    if not iso:
        return None
    try:
        moment = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return (datetime.datetime.now().date() - moment.date()).days

def human_when(iso: str) -> str:
    """"dziś 20:41" / "wczoraj 09:12" / "3 dni temu" / data."""
    if not iso:
        return "—"
    try:
        moment = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return "—"
    delta_days = age_days(iso)
    if delta_days == 0:
        return i18n.t("today {time}", time=f"{moment:%H:%M}")
    if delta_days == 1:
        return i18n.t("yesterday {time}", time=f"{moment:%H:%M}")
    if 1 < delta_days < 7:
        return i18n.t("{days} days ago", days=delta_days)
    return f"{moment:%d.%m.%Y %H:%M}"

def default_state_path() -> str:
    """%APPDATA%\\BackupTool\\backups.json (albo $BACKUPTOOL_STATE dla testów)."""
    override = os.environ.get("BACKUPTOOL_STATE")
    if override:
        return override
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIR_NAME, STATE_FILENAME)

def default_state() -> dict:
    return {"version": STATE_VERSION, "backups": [], "language": ""}

def _normalize_backup(raw) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    sources = [str(s) for s in (raw.get("sources") or []) if s]
    last_run = raw.get("last_run")
    return {
        "id": str(raw.get("id") or uuid.uuid4().hex),
        "name": str(raw.get("name") or "Backup"),
        "sources": sources,
        "destination": str(raw.get("destination") or ""),
        "use_zip": bool(raw.get("use_zip", True)),
        "app_data": normalize_app_data(raw.get("app_data")),
        "cloud": normalize_cloud(raw.get("cloud")),
        "created_at": raw.get("created_at") or now_iso(),
        "last_run": last_run if isinstance(last_run, dict) else None,
    }

def normalize_backups(raw) -> list:
    """Lista wpisów z surowych danych JSON, wspólna dla stanu i pliku listy."""
    if not isinstance(raw, list):
        return []
    return [_normalize_backup(item) for item in raw if isinstance(item, dict)]

def load_state(path: str | None = None) -> dict:
    """Wczytuje zapisane backupy; uszkodzony plik nie wywala aplikacji."""
    path = path or default_state_path()
    state = default_state()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, ValueError):
        return state
    if isinstance(raw, dict):
        state["backups"] = normalize_backups(raw.get("backups"))
        language = raw.get("language")
        if isinstance(language, str) and language in i18n.LANGUAGES:
            state["language"] = language
    return state

def save_state(state: dict, path: str | None = None) -> None:
    """Zapis atomowy — brak wpół zapisanego pliku stanu po awarii."""
    path = path or default_state_path()
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    payload = {"version": STATE_VERSION,
               "backups": [_normalize_backup(b) for b in state.get("backups", [])]}
    language = state.get("language")
    if isinstance(language, str) and language in i18n.LANGUAGES:
        payload["language"] = language
    tmp = path + TMP_SUFFIX
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    finally:
        _silent_remove(tmp)

def new_backup(name: str = "", sources=None, destination: str = "",
               use_zip: bool = True, app_data=None, cloud_settings=None) -> dict:
    """Nowy wpis backupu (jeszcze niezapisany)."""
    return {
        "id": uuid.uuid4().hex,
        "name": name or "",
        "sources": list(sources or []),
        "destination": destination or "",
        "use_zip": bool(use_zip),
        "app_data": normalize_app_data(app_data),
        "cloud": normalize_cloud(cloud_settings),
        "created_at": now_iso(),
        "last_run": None,
    }

def get_backup(state: dict, backup_id: str):
    for backup in state.get("backups", []):
        if backup.get("id") == backup_id:
            return backup
    return None

def put_backup(state: dict, backup: dict) -> None:
    """Dodaje albo podmienia backup o tym samym id."""
    backups = state.setdefault("backups", [])
    for index, existing in enumerate(backups):
        if existing.get("id") == backup.get("id"):
            backups[index] = backup
            return
    backups.append(backup)

def remove_backup(state: dict, backup_id: str) -> bool:
    backups = state.get("backups", [])
    for index, existing in enumerate(backups):
        if existing.get("id") == backup_id:
            del backups[index]
            return True
    return False

def duplicate_name(state: dict, name: str, exclude_id: str = "") -> bool:
    """Czy nazwa jest już zajęta przez inny backup (bez względu na wielkość liter)."""
    needle = (name or "").strip().casefold()
    if not needle:
        return False
    for backup in state.get("backups", []):
        if backup.get("id") == exclude_id:
            continue
        if (backup.get("name") or "").strip().casefold() == needle:
            return True
    return False

def _path_inside(child: str, parent: str) -> bool:
    """Czy child leży w parent (albo jest tym samym folderem)."""
    try:
        child_abs = os.path.normcase(os.path.abspath(child))
        parent_abs = os.path.normcase(os.path.abspath(parent))
    except (OSError, ValueError):
        return False
    return child_abs == parent_abs or child_abs.startswith(parent_abs + os.sep)

def missing_sources(backup: dict) -> list:
    """Źródła zapisane w backupie, których nie ma teraz na dysku.

    Po przywróceniu listy na innym komputerze ścieżki mogą nie istnieć,
    wtedy wiersz pokazuje „Wymaga konfiguracji” zamiast błędu po kliknięciu Start.
    """
    return [source for source in (backup.get("sources") or [])
            if source and not os.path.exists(source)]

def _drive_available(path: str) -> bool:
    """Czy dysk z tej ścieżki jest podłączony (D:\\ znika po restarcie na innym PC)."""
    drive, _ = os.path.splitdrive(os.path.abspath(path))
    if not drive:
        return True
    return os.path.exists(drive + os.sep)

def setup_problem(backup: dict):
    """Co trzeba poprawić, żeby backup ruszył, albo None, gdy wszystko gra."""
    missing = missing_sources(backup)
    if missing:
        return i18n.t("Source not found: {path}", path=missing[0])
    data = normalize_app_data(backup.get("app_data"))
    if not (backup.get("sources") or data["hermes"] or data["obsidian"]):
        return i18n.t("Add a source or enable app data (Hermes / Obsidian).")
    provider = cloud_provider(backup)
    if provider != "none":
        if not cloud.remote_ready(provider):
            return i18n.t("{provider} account is not connected — connect it in settings.",
                          provider=cloud.PROVIDER_LABELS.get(provider, provider))
        return None
    destination = (backup.get("destination") or "").strip()
    if not destination:
        return i18n.t("Choose a destination.")
    if not _drive_available(destination):
        drive = os.path.splitdrive(os.path.abspath(destination))[0]
        return i18n.t("Drive {drive} is not available on this computer.", drive=drive)
    return None

def validate_backup(backup: dict, state: dict | None = None, detection=None):
    """Zwraca komunikat błędu albo None, gdy backup można zapisać/uruchomić."""
    name = (backup.get("name") or "").strip()
    if not name:
        return i18n.t("Name your backup.")
    if state is not None and duplicate_name(state, name, backup.get("id", "")):
        return i18n.t("A backup named “{name}” already exists.", name=name)
    sources = [s for s in (backup.get("sources") or []) if s]
    data = normalize_app_data(backup.get("app_data"))
    uses_app_data = bool(data["hermes"] or data["obsidian"])
    if not sources and not uses_app_data:
        return i18n.t("Add a source or enable app data (Hermes / Obsidian).")
    missing = missing_sources(backup)
    if missing:
        return i18n.t("Source not found: {path}", path=missing[0])
    provider = cloud_provider(backup)
    destination = ""
    if provider != "none":
        if not cloud.remote_ready(provider):
            label = cloud.PROVIDER_LABELS.get(provider, provider)
            return i18n.t("{provider} account is not connected — connect it in settings.",
                          provider=label)
    else:
        destination = (backup.get("destination") or "").strip()
        if not destination:
            return i18n.t("Choose a destination.")
        if os.path.exists(destination) and not os.path.isdir(destination):
            return i18n.t("Destination must be a folder.")
        for source in sources:
            if os.path.isdir(source) and _path_inside(destination, source):
                return i18n.t("Destination cannot be inside the source folder.")

    if not uses_app_data:
        return None

    found = detection if detection is not None else appdata_detect.detect()
    protected = []
    if data["hermes"]:
        inventory = found.get("hermes")
        if not inventory:
            return i18n.t("Hermes data not found on this computer.")
        protected.append(inventory["root"])
        protected.extend(inventory.get("mnemosyne_dirs") or [])
        if inventory.get("mnemosyne_available") or inventory.get("builtin_available"):
            if data["memory"] == "mnemosyne" and not inventory.get("mnemosyne_available"):
                return i18n.t("Mnemosyne memory not found — choose the built-in one.")
            if data["memory"] == "builtin" and not inventory.get("builtin_available"):
                return i18n.t("Built-in memory not found — choose Mnemosyne.")
    if data["obsidian"]:
        vaults = (found.get("obsidian") or {}).get("vaults") or []
        if not vaults:
            return i18n.t("No Obsidian vaults found.")
        protected.extend(vaults)

    for path in protected if destination else ():
        if _path_inside(destination, path):
            return i18n.t("Destination cannot be inside the data you back up.")
    return None

def target_path(backup: dict) -> str:
    """Dokładna ścieżka, którą tworzy/nadpisuje backup (dla chmury: staging)."""
    name = sanitize_name(backup.get("name") or "Backup")
    if cloud_provider(backup) != "none":
        base = staging_path(backup)
        return os.path.join(base, name + ".zip")
    destination = os.path.normpath(backup.get("destination") or "")
    if use_zip_for(backup):
        return os.path.join(destination, name + ".zip")
    return os.path.join(destination, name)

def _unique_top_names(sources) -> list:
    """Nazwy najwyższego poziomu bez kolizji (dwa foldery "A" -> "A", "A (2)")."""
    used = {}
    result = []
    for source in sources:
        base = os.path.basename(os.path.normpath(source)) or "element"
        key = base.casefold()
        count = used.get(key, 0)
        used[key] = count + 1
        result.append(base if count == 0 else f"{base} ({count + 1})")
    return result

def _stat_of(path: str):
    """(rozmiar, mtime_ns) z jednego wywołania — po tym mapa rozpoznaje zmiany."""
    try:
        st = os.stat(path)
        return st.st_size, st.st_mtime_ns
    except OSError:
        return 0, 0

def _matches_skip(name: str, patterns) -> bool:
    """Wzorce: dokładna nazwa albo "*.rozszerzenie"."""
    lowered = name.lower()
    for pattern in patterns or ():
        if pattern.startswith("*."):
            if lowered.endswith(pattern[1:].lower()):
                return True
        elif lowered == pattern.lower():
            return True
    return False

def _matches_suffix(name: str, suffixes) -> bool:
    """Końcówki plików: ".db-wal", ".lock" itd."""
    lowered = name.lower()
    return any(lowered.endswith(suffix.lower()) for suffix in (suffixes or ()))

def manual_specs(sources) -> list:
    """Ręcznie dodane źródła jako specyfikacje do zebrania plików."""
    specs = []
    for source in sources:
        source = os.path.normpath(source)
        if os.path.isdir(source):
            specs.append({"kind": "dir", "root": source,
                          "label": os.path.basename(source) or "folder"})
        elif os.path.isfile(source):
            specs.append({"kind": "file", "path": source,
                          "label": os.path.basename(source)})
    return specs

def _unique_labels(specs) -> list:
    used = {}
    labels = []
    for spec in specs:
        base = spec.get("label") or "element"
        count = used.get(base.casefold(), 0)
        used[base.casefold()] = count + 1
        labels.append(base if count == 0 else f"{base} ({count + 1})")
    return labels

def _walk_dir(start: str, prefix: str, spec: dict, entries: list, report=None) -> None:
    skip_names = spec.get("skip_names") or ()
    skip_suffixes = spec.get("skip_suffixes") or ()
    skip_paths = {os.path.normcase(os.path.abspath(p))
                  for p in (spec.get("skip_paths") or ())}
    for visited, (dirpath, dirnames, filenames) in enumerate(os.walk(start)):
        if report and not visited % 64:
            report()
        dirnames[:] = [d for d in dirnames
                       if not _matches_skip(d, skip_names)
                       and os.path.normcase(os.path.abspath(os.path.join(dirpath, d)))
                       not in skip_paths]
        for filename in filenames:
            if _matches_skip(filename, skip_names) or _matches_suffix(filename, skip_suffixes):
                continue
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, start)
            entries.append((full, os.path.join(prefix, relative), *_stat_of(full)))

def _walk_spec(spec: dict, label: str, entries: list, report=None) -> None:
    root = spec["root"]
    includes = spec.get("include")
    if not includes:
        _walk_dir(root, label, spec, entries, report)
        return
    skip_names = spec.get("skip_names") or ()
    skip_suffixes = spec.get("skip_suffixes") or ()
    for name in includes:
        full = os.path.join(root, name)
        if os.path.isfile(full):
            if _matches_skip(name, skip_names) or _matches_suffix(name, skip_suffixes):
                continue
            entries.append((full, os.path.join(label, name), *_stat_of(full)))
        elif os.path.isdir(full):
            _walk_dir(full, os.path.join(label, name), spec, entries, report)

def collect_spec_entries(specs, progress=None) -> list:
    """[(plik, nazwa_w_backupie, rozmiar, mtime_ns)] z listy specyfikacji."""
    entries = []
    report = (lambda: progress(len(entries))) if progress else None
    for spec, label in zip(specs, _unique_labels(specs)):
        if spec.get("kind") == "file":
            entries.append((spec["path"], label, *_stat_of(spec["path"])))
        else:
            _walk_spec(spec, label, entries, report)
        if report:
            report()
    return entries

def collect_entries(sources) -> list:
    """Zawartość ręcznie wybranych źródeł (zachowane dla testów i zgodności)."""
    return collect_spec_entries(manual_specs(sources))

def resolve_specs(backup: dict, detection=None) -> list:
    """Wszystko, co realnie wejdzie do backupu: ręczne źródła + dane aplikacji."""
    specs = manual_specs([s for s in (backup.get("sources") or []) if s])
    data = normalize_app_data(backup.get("app_data"))
    if not (data["hermes"] or data["obsidian"]):
        return specs

    found = detection if detection is not None else appdata_detect.detect()
    if data["hermes"]:
        inventory = found.get("hermes")
        if not inventory:
            raise BackupError(i18n.t("Hermes data not found on this computer."))
        specs += appdata_detect.hermes_specs(inventory, data["memory"])
    if data["obsidian"]:
        vaults = appdata_detect.obsidian_specs(found.get("obsidian"))
        if not vaults:
            raise BackupError(i18n.t("No Obsidian vaults found."))
        specs += vaults
    return specs

def collect_backup_entries(backup: dict, detection=None, progress=None) -> list:
    return collect_spec_entries(resolve_specs(backup, detection), progress)

def _check_cancel(cancelled) -> None:
    if cancelled is not None and cancelled():
        raise Cancelled("Przerwano.")

def _is_sqlite(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False

@contextlib.contextmanager
def _readable_source(path: str):
    """Dla bazy SQLite w użyciu oddaje spójną migawkę (backup API), nie plik na żywo."""
    snapshot = None
    if path.lower().endswith(".db") and _is_sqlite(path):
        try:
            handle, snapshot = tempfile.mkstemp(suffix=".db", prefix="bt-snap-")
            os.close(handle)
            source = sqlite3.connect(path, timeout=2.0)
            target = sqlite3.connect(snapshot)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
        except (sqlite3.Error, OSError):
            if snapshot:
                _silent_remove(snapshot)
            snapshot = None
    try:
        yield snapshot if snapshot else path
    finally:
        if snapshot:
            _silent_remove(snapshot)

def _silent_remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass

def _dos_datetime(stamp) -> tuple:
    """(time, date) w formacie ZIP z krotki time.localtime()."""
    year, month, day, hour, minute, second = stamp[:6]
    if year < 1980:
        year, month, day = 1980, 1, 1
    return (hour << 11 | minute << 5 | second // 2,
            (year - 1980) << 9 | month << 5 | day)

class _ZipWriter:
    """Zapis ZIP bez zipfile — pozwala wstawić gotowe, już skompresowane wpisy."""

    UTF8_FLAG = 0x800

    def __init__(self, handle):
        self.handle = handle
        self.offset = 0
        self.items = []
        self.count = 0

    def add(self, name, stamp, crc, csize, usize, method, payload) -> None:
        # ZIP64 per wpis to osobna robota — powyżej 4 GB wolimy pełny backup.
        if usize > 0xFFFFFFFF or csize > 0xFFFFFFFF or self.offset > 0xFFFFFFFF:
            raise BackupError(i18n.t("File too large for the fast path."))
        raw_name = name.encode("utf-8")
        dos_time, dos_date = _dos_datetime(stamp)
        self.handle.write(struct.pack("<IHHHHHIIIHH", 0x04034B50, 20, self.UTF8_FLAG,
                                      method, dos_time, dos_date, crc, csize, usize,
                                      len(raw_name), 0))
        self.handle.write(raw_name)
        self.handle.write(payload)
        self.items.append((method, dos_time, dos_date, crc, csize, usize, raw_name,
                           self.offset))
        self.offset += 30 + len(raw_name) + len(payload)
        self.count += 1

    def close(self) -> None:
        cd_start = self.offset
        for method, dos_time, dos_date, crc, csize, usize, raw_name, offset in self.items:
            self.handle.write(struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20,
                                          self.UTF8_FLAG, method, dos_time, dos_date,
                                          crc, csize, usize, len(raw_name), 0, 0, 0, 0,
                                          0, offset))
            self.handle.write(raw_name)
            self.offset += 46 + len(raw_name)
        cd_size = self.offset - cd_start
        # Ponad 65 535 wpisów (PZ ma 251 tys.) wymaga końcówki ZIP64.
        if self.count >= 0xFFFF or cd_start >= 0xFFFFFFFF:
            z64_at = self.offset
            self.handle.write(struct.pack("<IQHHIIQQQQ", 0x06064B50, 44, 45, 45, 0, 0,
                                          self.count, self.count, cd_size, cd_start))
            self.handle.write(struct.pack("<IIQI", 0x07064B50, 0, z64_at, 1))
            count, size, offset = 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF
        else:
            count, size, offset = self.count, cd_size, cd_start
        self.handle.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, count, count,
                                      size, offset, 0))

def _raw_member(source, info) -> bytes:
    """Surowe, już skompresowane bajty wpisu z poprzedniego archiwum."""
    source.seek(info.header_offset)
    header = source.read(30)
    if len(header) != 30:
        raise BackupError(i18n.t("The previous archive is damaged."))
    sig, _ver, _flag, _method, _time, _date, _crc, _csize, _usize, name_len, extra_len = \
        struct.unpack("<IHHHHHIIIHH", header)
    if sig != 0x04034B50:
        raise BackupError(i18n.t("The previous archive is damaged."))
    source.seek(info.header_offset + 30 + name_len + extra_len)
    payload = source.read(info.compress_size)
    if len(payload) != info.compress_size:
        raise BackupError(i18n.t("The previous archive is damaged."))
    return payload

def _compress_data(data: bytes, method: int) -> tuple:
    """(crc, bajty, rozmiar_oryginalu) — deflate albo store."""
    crc = zlib.crc32(data) & 0xFFFFFFFF
    if method == zipfile.ZIP_STORED:
        return crc, data, len(data)
    compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
    return crc, compressor.compress(data) + compressor.flush(), len(data)

def _compress_file(path: str, method: int) -> tuple:
    with open(path, "rb") as handle:
        return _compress_data(handle.read(), method)

def _archive_is_sane(path: str, expected_count: int) -> bool:
    """CRC każdego wpisu — zanim podmienimy archiwum."""
    try:
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) != expected_count:
                return False
            return archive.testzip() is None
    except (OSError, zipfile.BadZipFile, ValueError):
        return False

def _incremental_zip(target: str, entries, backup: dict, progress=None,
                     cancelled=None):
    """Przebudowa ZIP z poprzedniego archiwum: niezmienione wpisy bez rekompresji.

    Zwraca (liczba_plików, mapa) albo None — wtedy trzeba zrobić pełny backup.
    """
    if not os.path.isfile(target):
        return None
    manifest = load_manifest(backup, target)
    if not manifest:
        return None
    tmp = target + TMP_SUFFIX
    try:
        with zipfile.ZipFile(target) as archive:
            index = {info.filename: info for info in archive.infolist()}
        if not index:
            return None
        with open(target, "rb") as source, open(tmp, "wb") as handle:
            writer = _ZipWriter(handle)
            new_map = {}

            def cached(info, entry, size, mtime_ns):
                return (info is not None and entry is not None
                        and int(entry[0]) == size and int(entry[1]) == mtime_ns
                        and info.file_size == size)

            plan = []
            for _path, arcname, size, mtime_ns in entries:
                name = arcname.replace(os.sep, "/")
                plan.append(cached(index.get(name), manifest.get(name), size, mtime_ns))
            total_changed = plan.count(False)
            changed_done = 0
            for (path, arcname, size, mtime_ns), unchanged in zip(entries, plan):
                _check_cancel(cancelled)
                name = arcname.replace(os.sep, "/")
                info = index.get(name)
                if unchanged:
                    payload = _raw_member(source, info)
                    stamp = (info.date_time + (0, 0, 0))[:6]
                    writer.add(name, stamp, info.CRC, info.compress_size,
                               info.file_size, info.compress_type, payload)
                else:
                    if size > 256 * 1024 * 1024:
                        raise BackupError(i18n.t("File too large for the fast path."))
                    method = (zipfile.ZIP_STORED if is_archive(path)
                              else zipfile.ZIP_DEFLATED)
                    with _readable_source(path) as readable:
                        stat = os.stat(readable)
                        stamp = time.localtime(stat.st_mtime)
                        crc, payload, original = _compress_file(readable, method)
                    writer.add(name, stamp, crc, len(payload), original, method, payload)
                    changed_done += 1
                    if progress and total_changed:
                        progress(changed_done, total_changed, "changed")
                new_map[name] = [size, mtime_ns]
            writer.close()
        if writer.count != len(entries) or not _archive_is_sane(tmp, len(entries)):
            _silent_remove(tmp)
            return None
        os.replace(tmp, target)
        return writer.count, new_map
    except (BackupError, zipfile.BadZipFile, OSError):
        _silent_remove(tmp)
        return None
    except BaseException:
        _silent_remove(tmp)
        raise

def _write_zip(target: str, entries, progress=None, cancelled=None):
    """Pełne archiwum od zera. Zwraca (liczba_plików, mapa plików)."""
    tmp = target + TMP_SUFFIX
    done = 0
    manifest = {}
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED,
                             compresslevel=6, allowZip64=True) as archive:
            for index, (source, arcname, size, mtime_ns) in enumerate(entries, 1):
                _check_cancel(cancelled)
                with _readable_source(source) as readable:
                    if is_archive(source):
                        archive.write(readable, arcname=arcname,
                                      compress_type=zipfile.ZIP_STORED)
                    else:
                        archive.write(readable, arcname=arcname,
                                      compress_type=zipfile.ZIP_DEFLATED)
                manifest[arcname.replace(os.sep, "/")] = [size, mtime_ns]
                done = index
                if progress:
                    progress(done, len(entries), arcname)
        os.replace(tmp, target)
        return done, manifest
    except BaseException:
        _silent_remove(tmp)
        raise

def _archive_matches(target: str, entries, manifest) -> bool:
    """Czy archiwum i mapa dokładnie odpowiadają temu, co leży na dysku."""
    if not manifest or not os.path.isfile(target):
        return False
    try:
        with zipfile.ZipFile(target) as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile):
        return False
    if len(infos) != len(entries):
        return False
    index = {info.filename: info for info in infos}
    for _path, arcname, size, mtime_ns in entries:
        name = arcname.replace(os.sep, "/")
        info = index.get(name)
        cached = manifest.get(name)
        if info is None or cached is None:
            return False
        if int(cached[0]) != size or int(cached[1]) != mtime_ns:
            return False
        if info.file_size != size:
            return False
    return True

def _sync_archive(backup: dict, target: str, entries, progress=None,
                  cancelled=None) -> tuple:
    """ZIP: nic się nie zmieniło? / przyrost z poprzedniego archiwum / pełny zapis.

    Zwraca (liczba_plików, czy_trzeba_wysyłać).
    """
    manifest = load_manifest(backup, target)
    if _archive_matches(target, entries, manifest):
        return len(entries), False
    fast = _incremental_zip(target, entries, backup, progress, cancelled)
    if fast is not None:
        count, new_map = fast
    else:
        count, new_map = _write_zip(target, entries, progress, cancelled)
    save_manifest(backup, target, new_map)
    return count, True

def _copy_files(target: str, entries, progress=None, cancelled=None) -> int:
    os.makedirs(target, exist_ok=True)
    done = 0
    for index, (source, arcname, _size, _mtime) in enumerate(entries, 1):
        _check_cancel(cancelled)
        destination = os.path.join(target, arcname)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with _readable_source(source) as readable:
            shutil.copy2(readable, destination)
        done = index
        if progress:
            progress(done, len(entries), arcname)
    return done

def run_backup(backup: dict, progress=None, cancelled=None, detection=None) -> dict:
    """Wykonuje backup i zwraca wynik — nigdy nie rzuca wyjątkiem."""
    result = {"ok": False, "cancelled": False, "target": "", "files": 0,
              "bytes": 0, "seconds": 0.0, "message": "", "at": now_iso(),
              "needs_reauth": False}
    started = time.perf_counter()
    try:
        error = validate_backup(backup, detection=detection)
        if error:
            raise BackupError(error)
        destination = backup.get("destination") or ""
        use_zip = use_zip_for(backup)
        target = target_path(dict(backup, use_zip=use_zip))
        provider = cloud_provider(backup)
        # Sesja sprawdzona PRZED pakowaniem: wygasły token nie ma sensu
        # kosztować minut zipowania, a UI od razu pokazuje „Odnów sesję".
        if provider != "none":
            cloud.require_session(provider)
        result["target"] = display_target(dict(backup, use_zip=use_zip))             if provider != "none" else target
        os.makedirs(os.path.dirname(target) or destination, exist_ok=True)
        expected = 0
        if use_zip:
            try:
                expected = len(load_manifest(backup, target) or {})
            except (OSError, TypeError, ValueError):
                expected = 0
        if progress:
            progress(0, expected, "scan")
        entries = collect_backup_entries(
            backup, detection,
            progress=(lambda found: progress(found, expected, "scan")) if progress else None)
        result["bytes"] = sum(item[2] for item in entries)
        if progress:
            progress(0, 0 if use_zip else len(entries), "")
        needs_upload = True
        if use_zip:
            result["files"], needs_upload = _sync_archive(backup, target, entries,
                                                         progress, cancelled)
        else:
            result["files"] = _copy_files(target, entries, progress, cancelled)
        if provider != "none" and needs_upload:
            if progress:
                progress(0, 0, "Wysyłanie do chmury…")
            cloud.prepare_upload(
                backup, target,
                on_status=lambda text: progress(0, 0, text) if progress else None,
                on_percent=lambda pct: progress(pct, 100, f"upload:{pct}")
                if progress else None,
                should_stop=cancelled)
        result["ok"] = True
        if not needs_upload:
            result["unchanged"] = True
            result["message"] = i18n.t("Nothing changed — the copy is up to date.")
        else:
            result["message"] = (i18n.t("Done and uploaded") if provider != "none"
                                 else i18n.t("Done"))
    except Cancelled:
        result["cancelled"] = True
        result["message"] = i18n.t("Stopped")
    except cloud.CloudAuthError as exc:
        # Sesja padła (Google: 7 dni w trybie Testing) — jedno kliknięcie ją
        # odnowi tym samym client ID, a kopia pójdzie ponownie.
        result["needs_reauth"] = True
        result["message"] = str(exc) or exc.__class__.__name__
    except (BackupError, OSError, zipfile.BadZipFile, shutil.Error,
            cloud.CloudError) as exc:
        result["message"] = str(exc) or exc.__class__.__name__
    except Exception as exc:  # noqa: BLE001 - wynik zawsze wraca do UI
        result["message"] = f"{exc.__class__.__name__}: {exc}"
    if cloud_provider(backup) != "none":
        # Gotowe archiwum zostaje jako baza dla następnego przebiegu przyrostowego.
        _cleanup_parts(staging_path(backup))
    result["seconds"] = round(time.perf_counter() - started, 1)
    return result

def apply_result(backup: dict, result: dict) -> dict:
    """Zapisuje wynik w wpisie backupu (to ląduje w pliku stanu)."""
    backup["last_run"] = {
        "at": result.get("at") or now_iso(),
        "ok": bool(result.get("ok")),
        "cancelled": bool(result.get("cancelled")),
        "message": result.get("message", ""),
        "target": result.get("target", ""),
        "files": int(result.get("files") or 0),
        "bytes": int(result.get("bytes") or 0),
        "seconds": float(result.get("seconds") or 0),
        "needs_reauth": bool(result.get("needs_reauth")),
    }
    return backup
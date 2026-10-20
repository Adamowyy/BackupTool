"""Lista backupów jako przenośny plik: zapis, odczyt i wymiana z chmurą.

Po formacie komputera wystarczy zainstalować BackupTool i wskazać plik listy
w menu „Przywróć listę”, a wpisy wracają razem ze źródłami, celem zapisu
i ustawieniami chmury. Pliki kopii nie są ruszane: przenosi się tylko lista.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile

import backup_core as core
import cloud
import i18n

LIST_FILE = "backup-list.json"
LIST_FOLDER = "BackupTool"
PAYLOAD_KIND = "backuptool-list"
PAYLOAD_VERSION = 1
TMP_SUFFIX = ".part"


class ListError(Exception):
    """Lista nieczytelna albo obca, komunikat gotowy dla użytkownika."""


def now_iso() -> str:
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def build_payload(state: dict) -> dict:
    """Zawartość pliku listy: nagłówek wersji plus wpisy backupów."""
    backups = []
    for backup in state.get("backups", []):
        entry = dict(backup)
        entry["sources"] = list(backup.get("sources") or [])
        backups.append(entry)
    return {"kind": PAYLOAD_KIND, "version": PAYLOAD_VERSION,
            "created_at": now_iso(), "backups": backups}


def dump_payload(payload: dict, path: str) -> None:
    """Zapis atomowy, więc przerwany zapis nie zostawia połowy pliku listy."""
    folder = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(folder, exist_ok=True)
        tmp = path + TMP_SUFFIX
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError) as exc:
        try:
            os.remove(tmp)
        except (OSError, UnboundLocalError):
            pass
        raise ListError(i18n.t("Could not save the list: {message}",
                               message=exc)) from exc


def read_payload(path: str) -> dict:
    """Wczytuje plik listy: {"backups": [...], "created_at": "..."}.

    Odrzuca pliki obce i puste listy: przywrócenie niczego nie ma sensu,
    a wyczyszczenie obecnej listy byłoby trudną do cofnięcia pomyłką.
    """
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            raw = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ListError(i18n.t("Could not read the list: {message}",
                               message=exc)) from exc

    if not isinstance(raw, dict) or raw.get("kind", PAYLOAD_KIND) != PAYLOAD_KIND:
        raise ListError(i18n.t("This file is not a BackupTool list."))

    backups = core.normalize_backups(raw.get("backups"))
    if not backups:
        raise ListError(i18n.t("This list is empty — there is nothing to restore."))
    created = raw.get("created_at")
    return {"backups": backups,
            "created_at": created if isinstance(created, str) else ""}


def suggested_filename() -> str:
    """backup-list-2026-10-20.json, czyli data w nazwie, żeby pliki się nie myliły."""
    stem = os.path.splitext(LIST_FILE)[0]
    return f"{stem}-{datetime.date.today():%Y-%m-%d}.json"


def missing_sources(backups) -> int:
    """Ile źródeł z listy nie istnieje na tym komputerze (np. po formacie)."""
    return sum(len(core.missing_sources(backup)) for backup in backups or [])


def _list_temp_dir() -> str:
    return tempfile.mkdtemp(prefix="bt-list-")


def cloud_upload(payload: dict, provider: str, on_percent=None) -> dict:
    """Wysyła listę do chmury i potwierdza, że plik rzeczywiście tam jest."""
    workdir = _list_temp_dir()
    try:
        local = os.path.join(workdir, LIST_FILE)
        dump_payload(payload, local)
        cloud.upload_file(local, provider, LIST_FOLDER, on_percent=on_percent)
    except cloud.CloudError as exc:
        raise ListError(i18n.t("Could not save the list: {message}",
                               message=exc)) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    info = cloud.remote_file(provider, LIST_FOLDER, LIST_FILE)
    if not info:
        raise ListError(i18n.t("The list did not reach the cloud."))
    return info


def cloud_download(provider: str) -> dict:
    """Pobiera listę z chmury do pliku tymczasowego i zwraca jej zawartość."""
    info = cloud.remote_file(provider, LIST_FOLDER, LIST_FILE)
    if not info:
        raise ListError(i18n.t("No list in the cloud yet — save it first."))

    workdir = _list_temp_dir()
    local = os.path.join(workdir, LIST_FILE)
    try:
        cloud.download_file(local, provider, LIST_FOLDER, LIST_FILE)
        payload = read_payload(local)
    except cloud.CloudError as exc:
        raise ListError(i18n.t("Could not restore the list: {message}",
                               message=exc)) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    payload["info"] = info
    return payload

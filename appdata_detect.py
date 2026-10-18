#!/usr/bin/env python3
"""Wykrywanie danych Hermesa i Obsidiana na danym komputerze."""

from __future__ import annotations

import glob
import json
import os
import re

HERMES_MARKERS = ("config.yaml", "sessions", "skills", "mnemosyne",
                  "memory_store.db", "memories", "plugins")

HERMES_INCLUDE = (
    "config.yaml",
    "SOUL.md",
    "skills",
    "scripts",
    "assets",
    "plugins",
    "desktop-plugins",
    "hooks",
    "cron",
    "vault",
    "shared",
    "skins",
    "kanban.db",
    "projects.db",
)
HERMES_SKIP_NAMES = {
    "__pycache__", ".git", ".cache", "node_modules", "logs", "locks", "index-cache",
    "*.lock", "*.pid", "*.pyc",
    "auth.json", "nous_auth.json", "connections.json", "credentials.json",
    ".env", "*.env",
}

OBSIDIAN_CONFIGS = (
    os.path.join(os.environ.get("APPDATA", ""), "obsidian", "obsidian.json"),
    os.path.join(os.environ.get("APPDATA", ""), "Obsidian", "obsidian.json"),
    os.path.expanduser("~/Library/Application Support/obsidian/obsidian.json"),
    os.path.expanduser("~/.config/obsidian/obsidian.json"),
)

OBSIDIAN_SEARCH_ROOTS = (
    "~/Documents",
    "~/OneDrive/Documents",
    "~/OneDrive",
    "~/Desktop",
    "~/Dokumenty",
)

def _hermes_candidates() -> list:
    candidates = []
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        candidates.append(env_home)
    candidates += [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "hermes"),
        os.path.join(os.environ.get("APPDATA", ""), "hermes"),
        os.path.expanduser("~/.hermes"),
        os.path.expanduser("~/.local/share/hermes"),
        os.path.expanduser("~/Library/Application Support/hermes"),
    ]
    unique = []
    seen = set()
    for path in candidates:
        if not path:
            continue
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(os.path.normpath(path))
    return unique

def _looks_like_hermes(path: str) -> bool:
    if not path or not os.path.isdir(path):
        return False
    found = sum(1 for marker in HERMES_MARKERS
                if os.path.exists(os.path.join(path, marker)))
    return found >= 2 or os.path.isfile(os.path.join(path, "config.yaml"))

def _memory_provider(config_path: str):
    """Jaki provider pamięci ma włączony Hermes (mnemosyne / wbudowana)."""
    try:
        with open(config_path, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return None
    inside = False
    for line in lines:
        if re.match(r"^memory:\s*$", line):
            inside = True
            continue
        if not inside:
            continue
        if re.match(r"^\S", line):
            break
        match = re.match(r"^\s+provider:\s*['\"]?([\w.-]+)", line)
        if match:
            return match.group(1).lower()
    return None

def _mnemosyne_dirs(root: str, include_user_dir: bool = True) -> list:
    dirs = []
    candidates = [os.path.join(root, "mnemosyne")]
    if include_user_dir:
        candidates.append(os.path.expanduser("~/.hermes/mnemosyne"))
    for candidate in candidates:
        data = os.path.join(candidate, "data")
        if not os.path.isdir(data):
            continue
        if not any(name.lower().endswith(".db") for name in os.listdir(data)):
            continue
        key = os.path.normcase(os.path.abspath(candidate))
        if key in {os.path.normcase(os.path.abspath(d)) for d in dirs}:
            continue
        dirs.append(os.path.normpath(candidate))
    return dirs

def hermes_inventory(root: str, include_user_dir: bool = True) -> dict:
    """Co Hermes ma na dysku: ścieżki do kopiowania i tryb pamięci."""
    mnemo_dirs = _mnemosyne_dirs(root, include_user_dir=include_user_dir)
    memories_dir = os.path.join(root, "memories")
    builtin_files = []
    if os.path.isdir(memories_dir):
        for name in sorted(os.listdir(memories_dir)):
            full = os.path.join(memories_dir, name)
            if os.path.isfile(full):
                builtin_files.append(full)
    for name in ("memory_store.db", "memories.json"):
        full = os.path.join(root, name)
        if os.path.isfile(full):
            builtin_files.append(full)

    mnemosyne_available = bool(mnemo_dirs)
    builtin_available = bool(builtin_files)

    provider = _memory_provider(os.path.join(root, "config.yaml"))
    if provider == "mnemosyne" or (provider is None and mnemosyne_available):
        preferred = "mnemosyne" if mnemosyne_available else "builtin"
    elif builtin_available:
        preferred = "builtin"
    else:
        preferred = "mnemosyne" if mnemosyne_available else "builtin"

    return {
        "root": root,
        "mnemosyne_available": mnemosyne_available,
        "builtin_available": builtin_available,
        "preferred_memory": preferred,
        "mnemosyne_dirs": mnemo_dirs,
        "provider": provider,
    }

def detect_hermes(candidates=None):
    """Pierwszy folder, który naprawdę wygląda na dane Hermesa."""
    for candidate in (candidates if candidates is not None else _hermes_candidates()):
        if _looks_like_hermes(candidate):
            return hermes_inventory(candidate)
    return None

def _read_obsidian_config(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return []
    vaults = data.get("vaults")
    result = []
    if isinstance(vaults, dict):
        for entry in vaults.values():
            if isinstance(entry, dict) and entry.get("path"):
                result.append(str(entry["path"]))
    return result

def _shallow_vault_search() -> list:
    found = []
    for root in OBSIDIAN_SEARCH_ROOTS:
        base = os.path.expanduser(root)
        if not os.path.isdir(base):
            continue
        try:
            children = sorted(os.listdir(base))[:200]
        except OSError:
            continue
        for name in children:
            full = os.path.join(base, name)
            if os.path.isdir(os.path.join(full, ".obsidian")):
                found.append(full)
    return found

def detect_obsidian():
    """Sejfy Obsidiana — z jego własnego rejestru, z fallbackiem na Documents."""
    vaults = []
    source = None
    for config_path in OBSIDIAN_CONFIGS:
        if not config_path or not os.path.isfile(config_path):
            continue
        paths = _read_obsidian_config(config_path)
        if paths:
            source = config_path
            for path in paths:
                if os.path.isdir(path):
                    vaults.append(os.path.normpath(path))
            break
    if not vaults:
        vaults = [os.path.normpath(p) for p in _shallow_vault_search()]

    unique = []
    seen = set()
    for path in vaults:
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)

    return {"vaults": unique, "config": source}

def detect() -> dict:
    """Pełna detekcja dla UI: {'hermes': {...}|None, 'obsidian': {...}}."""
    return {"hermes": detect_hermes(), "obsidian": detect_obsidian()}

def hermes_specs(inventory: dict, memory: str) -> list:
    """Specyfikacje źródeł backupu danych Hermesa (gotowe do collect)."""
    root = inventory["root"]
    specs = []
    include = [name for name in HERMES_INCLUDE if os.path.exists(os.path.join(root, name))]

    if memory == "mnemosyne":
        for directory in inventory.get("mnemosyne_dirs") or []:
            data_dir = os.path.join(directory, "data")
            label = "Hermes/Mnemosyne" if len(inventory["mnemosyne_dirs"]) == 1 else \
                f"Hermes/Mnemosyne ({os.path.basename(os.path.dirname(directory)) or directory})"
            specs.append({"kind": "dir", "root": data_dir, "label": label,
                          "skip_names": HERMES_SKIP_NAMES,
                          "skip_suffixes": (".db-shm", ".db-wal", ".init.lock")})
            config = os.path.join(directory, "config.yaml")
            if os.path.isfile(config):
                specs.append({"kind": "file", "path": config,
                              "label": label + "/config.yaml"})
    else:
        memories_dir = os.path.join(root, "memories")
        if os.path.isdir(memories_dir):
            include.append("memories")
        for name in ("memory_store.db", "memories.json"):
            if os.path.isfile(os.path.join(root, name)):
                include.append(name)

    if include:
        specs.insert(0, {"kind": "dir", "root": root, "label": "Hermes",
                         "include": include, "skip_names": HERMES_SKIP_NAMES,
                         "skip_suffixes": (".db-shm", ".db-wal", ".lock")})
    return specs

def obsidian_specs(detection: dict) -> list:
    specs = []
    for vault in (detection or {}).get("vaults", []):
        specs.append({
            "kind": "dir", "root": vault, "label": "Obsidian/" + os.path.basename(vault.rstrip("\\/")),
            "skip_names": {".trash", ".git", "node_modules", "__pycache__"},
            "skip_paths": {os.path.join(vault, ".obsidian", "cache")},
            "skip_suffixes": (),
        })
    return specs
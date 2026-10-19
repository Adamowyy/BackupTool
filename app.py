import os
import queue
import sys
import threading
import time
import traceback
from tkinter import filedialog, messagebox

import customtkinter as ctk

import appdata_detect
import backup_core as core
import cloud
import i18n

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

APP_NAME = "BackupTool"

BG = "#141518"
CARD = "#1e2126"
CARD_HOVER = "#23272e"
CARD_SEL = "#242a33"
BORDER = "#2b3038"
TEXT = "#e6e8ec"
MUTED = "#9aa0aa"
SUBTLE = "#6b7280"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"
ON_ACCENT = "#ffffff"
OK_BG = "#12351f"
OK_TEXT = "#4ade80"
ERR_BG = "#3a1a1d"
ERR_TEXT = "#f87171"
WARN_TEXT = "#fbbf24"
DANGER = "#dc2626"
DANGER_SOFT = "#3a1a1d"
DANGER_SOFT_HOVER = "#4a2125"
INFO_TEXT = "#93c5fd"

F_TITLE = ("Segoe UI", 22, "bold")
F_PANEL = ("Segoe UI", 14, "bold")
F_NAME = ("Segoe UI", 15, "bold")
F_TEXT = ("Segoe UI", 13)
F_SMALL = ("Segoe UI", 12)
F_MUTED = ("Segoe UI", 11)
F_BADGE = ("Segoe UI", 11, "bold")
F_BUTTON = ("Segoe UI", 13, "bold")

def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)

def enable_dark_titlebar(window):
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass

def plural(count, one, few, many):
    if count == 1:
        return f"{count} {i18n.t(one)}"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} {i18n.t(few)}"
    return f"{count} {i18n.t(many)}"

def short_path(path, limit=78):
    if not path or len(path) <= limit:
        return path
    parts = path.replace("/", "\\").split("\\")
    if len(parts) <= 3:
        return path[: max(1, limit - 1)] + "…"
    head = parts[0] + "\\"
    tail = []
    for part in reversed(parts[1:]):
        candidate = [part] + tail
        if len(head) + 3 + len("\\".join(candidate)) > limit:
            break
        tail = candidate
    if not tail:
        tail = [parts[-1]]
    return head + "…\\" + "\\".join(tail)

def make_button(parent, text, command, **kwargs):
    state = {"last": 0.0}

    def fire():
        now = time.monotonic()
        if now - state["last"] < 0.4:
            return
        state["last"] = now
        command()

    return ctk.CTkButton(parent, text=text, command=fire, **kwargs)

class BackupApp:
    IDLE = "Click Start to refresh a copy."
    EMPTY = "Add your first backup to get started."

    def __init__(self, root):
        self.root = root
        self.state = core.load_state()
        self.detection = appdata_detect.detect()
        i18n.set_language(self.state.get("language") or i18n.DEFAULT_LANGUAGE)
        self._queue = queue.Queue()
        self._detail_labels = {}
        self._start_buttons = {}
        self._running_id = None
        self._batch_queue = []
        self._batch_total = 0
        self._batch_ok = 0
        self._batch_errors = 0
        self._cancel_flag = threading.Event()
        self._worker = None

        self._build_ui()
        self._refresh_list()
        self.root.after(80, self._poll_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        root = self.root
        root.title(APP_NAME)
        root.geometry("1080x720")
        root.minsize(820, 560)
        root.configure(fg_color=BG)

        icon = resource_path("icon.ico")
        if os.path.exists(icon):
            try:
                root.iconbitmap(icon)
            except Exception:
                pass

        header = ctk.CTkFrame(root, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20, 14))

        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left")

        title_row = ctk.CTkFrame(titles, fg_color="transparent")
        title_row.pack(anchor="w")
        mark = ctk.CTkFrame(title_row, fg_color=ACCENT, corner_radius=3,
                            width=7, height=24)
        mark.pack(side="left", padx=(0, 10))
        mark.pack_propagate(False)
        ctk.CTkLabel(title_row, text=i18n.t("BackupTool"), font=F_TITLE,
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(titles, text=i18n.t("Backups of folders and files — one click."),
                     font=F_SMALL, text_color=MUTED).pack(anchor="w", padx=(17, 0),
                                                          pady=(2, 0))

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.pack(side="right")

        self.btn_new = make_button(
            actions, i18n.t("+  New backup"), self._new_backup, width=160, height=40,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
            corner_radius=10, font=F_BUTTON)
        self.btn_new.pack(side="right")

        lang_box = ctk.CTkFrame(actions, fg_color="transparent")
        lang_box.pack(side="right", padx=(0, 10))
        for code in i18n.LANGUAGES:
            active = code == i18n.language()
            make_button(
                lang_box, i18n.LABELS[code], lambda c=code: self.set_language(c),
                width=40, height=30, fg_color=CARD_SEL if active else "transparent",
                hover_color=CARD_SEL, text_color=TEXT if active else MUTED,
                border_width=1, border_color=ACCENT if active else BORDER,
                corner_radius=7, font=F_MUTED).pack(side="left", padx=(4, 0))

        main = ctk.CTkFrame(root, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=24)

        list_head = ctk.CTkFrame(main, fg_color="transparent")
        list_head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(list_head, text=i18n.t("Your backups"), font=F_PANEL,
                     text_color=TEXT).pack(side="left")
        self.lbl_count = ctk.CTkLabel(list_head, text="", font=F_MUTED,
                                      text_color=MUTED, fg_color=CARD_SEL,
                                      corner_radius=6, height=20, padx=8)
        self.lbl_count.pack(side="left", padx=(12, 0))
        self.btn_all = make_button(list_head, i18n.t("▶   Run all"), self._start_all,
                                   width=176, height=30, fg_color="transparent",
                                   hover_color=CARD_SEL, text_color=ACCENT,
                                   border_width=1, border_color=ACCENT,
                                   corner_radius=8, font=F_SMALL)
        self.btn_all.pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(
            main, fg_color=CARD, corner_radius=14,
            scrollbar_button_color=BORDER, scrollbar_button_hover_color=SUBTLE)
        self.scroll.pack(fill="both", expand=True, pady=(0, 12))

        self.footer = ctk.CTkFrame(root, fg_color="transparent")
        self.footer.pack(fill="x", padx=24, pady=(0, 16))

        self.progress_row = ctk.CTkFrame(self.footer, fg_color="transparent")
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_row, height=6, corner_radius=3, mode="indeterminate",
            progress_color=ACCENT, fg_color=BORDER)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        self.progress_bar.set(0)
        self.lbl_progress = ctk.CTkLabel(self.progress_row, text="", font=F_MUTED,
                                         text_color=MUTED, width=90)
        self.lbl_progress.pack(side="right", padx=(12, 0))

        self.status = ctk.CTkLabel(self.footer, text=i18n.t(self.IDLE), font=F_MUTED,
                                   text_color=SUBTLE, anchor="w", justify="left",
                                   wraplength=1000)
        self.status.pack(fill="x", pady=(6, 0))

        self.root.after(150, lambda: enable_dark_titlebar(self.root))

    def set_language(self, language):
        if language not in i18n.LANGUAGES or language == i18n.language():
            return
        i18n.set_language(language)
        self.state["language"] = language
        core.save_state(self.state)
        self.root.after(20, self._rebuild_ui)

    def _rebuild_ui(self):
        try:
            for widget in self.root.winfo_children():
                widget.destroy()
        except Exception:
            pass
        self._detail_labels = {}
        self._start_buttons = {}
        self._build_ui()
        self._refresh_list()
        if self._running_id:
            self._set_status(i18n.t("Copying…"), MUTED)

    def _refresh_list(self):
        for widget in self.scroll.winfo_children():
            widget.destroy()
        self._detail_labels = {}
        self._start_buttons = {}

        backups = self.state.get("backups", [])
        if backups:
            self.lbl_count.configure(
                text=plural(len(backups), "backup", "backups", "backups5"))
            if not self.lbl_count.winfo_manager():
                self.lbl_count.pack(side="left", padx=(12, 0))
            if self.status.cget("text") == i18n.t(self.EMPTY):
                self._set_status(i18n.t(self.IDLE), SUBTLE)
        else:
            self.lbl_count.pack_forget()
            if self.status.cget("text") == i18n.t(self.IDLE):
                self._set_status(i18n.t(self.EMPTY), SUBTLE)

        try:
            if backups:
                self.scroll._scrollbar.grid()
            else:
                self.scroll._scrollbar.grid_remove()
        except Exception:
            pass

        running = bool(self._running_id or self._batch_queue)
        self.btn_all.configure(
            text=i18n.t("■   Stop") if running else i18n.t("▶   Run all"),
            border_color=DANGER if running else ACCENT,
            text_color=ERR_TEXT if running else ACCENT,
            state="normal" if backups else "disabled")

        if not backups:
            self._build_empty_state()
            return

        ctk.CTkFrame(self.scroll, fg_color="transparent", height=4).pack(fill="x")
        for backup in backups:
            self._make_card(backup)

    def _build_empty_state(self):
        box = ctk.CTkFrame(self.scroll, fg_color="transparent")
        box.pack(fill="both", expand=True, pady=(80, 80))
        ctk.CTkLabel(box, text=i18n.t("No backups yet"), font=F_PANEL,
                     text_color=TEXT).pack()
        ctk.CTkLabel(box, text=i18n.t("Pick a folder or a file, name the copy and "
                                      "choose where it lives."),
                     font=F_SMALL, text_color=MUTED).pack(pady=(6, 16))
        make_button(box, i18n.t("Create your first backup"), self._new_backup,
                    width=190, height=40, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                    text_color=ON_ACCENT, corner_radius=10,
                    font=F_BUTTON).pack()

    def _make_card(self, backup):
        card = ctk.CTkFrame(self.scroll, fg_color=CARD_HOVER, corner_radius=12,
                            border_width=1, border_color=BORDER)
        card.pack(fill="x", padx=8, pady=(0, 10))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=13)

        actions = ctk.CTkFrame(inner, fg_color="transparent")
        actions.pack(side="right", padx=(16, 0))
        running = backup["id"] == self._running_id
        style = dict(fg_color=DANGER_SOFT, hover_color=DANGER_SOFT_HOVER,
                     text_color=ERR_TEXT, border_width=0) if running else \
            dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT)
        action = (lambda bid=backup["id"]: self._toggle_run(bid)) if running else \
            (lambda bid=backup["id"]: self._start_run(bid))
        btn_start = make_button(actions, i18n.t("Stop") if running else i18n.t("Start"),
                                action, width=96, height=34, corner_radius=9,
                                font=F_BUTTON, **style)
        btn_start.pack(side="right")
        make_button(actions, i18n.t("Open settings"),
                    lambda bid=backup["id"]: self._edit_backup(bid),
                    width=112, height=34, fg_color="transparent", hover_color=CARD_SEL,
                    text_color=MUTED, border_width=1, border_color=BORDER,
                    corner_radius=9, font=F_SMALL).pack(side="right", padx=(0, 8))

        info = ctk.CTkFrame(inner, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)

        name_row = ctk.CTkFrame(info, fg_color="transparent")
        name_row.pack(fill="x")
        ctk.CTkLabel(name_row, text=backup.get("name") or "-", font=F_NAME,
                     text_color=TEXT, anchor="w").pack(side="left")
        text, fg, fg_text = self._badge_for(backup)
        ctk.CTkLabel(name_row, text=text, font=F_BADGE, text_color=fg_text,
                     fg_color=fg, corner_radius=6, height=22, padx=9).pack(
            side="left", padx=(10, 0))

        ctk.CTkLabel(info, text=self._sources_line(backup), font=F_SMALL,
                     text_color=MUTED, anchor="w", wraplength=560).pack(
            fill="x", pady=(5, 0))
        label = ctk.CTkLabel(info, text=self._target_line(backup), font=F_SMALL,
                             text_color=SUBTLE, anchor="w", justify="left",
                             wraplength=560)
        label.pack(fill="x", pady=(2, 0))
        self._detail_labels[backup["id"]] = label
        self._start_buttons[backup["id"]] = btn_start

    def _badge_for(self, backup):
        if backup["id"] == self._running_id:
            return (i18n.t("Running…"), CARD_SEL, ACCENT)
        last = backup.get("last_run")
        if not last:
            return (i18n.t("New"), CARD_SEL, SUBTLE)
        if last.get("cancelled"):
            return (i18n.t("Stopped"), CARD_SEL, WARN_TEXT)
        if last.get("ok"):
            return (f"{i18n.t('Ready')} · {core.human_when(last.get('at'))}", OK_BG, OK_TEXT)
        return (i18n.t("Error"), ERR_BG, ERR_TEXT)

    def _sources_line(self, backup):
        data = core.normalize_app_data(backup.get("app_data"))
        chips = []
        if data["hermes"]:
            memory = "Mnemosyne" if data["memory"] == "mnemosyne" else i18n.t("Built-in")
            chips.append(f"Hermes ({memory})")
        if data["obsidian"]:
            vaults = (self.detection.get("obsidian") or {}).get("vaults") or []
            chips.append("Obsidian" + (f" ({plural(len(vaults), 'vault', 'vaults', 'vaults5')})"
                                       if vaults else ""))
        sources = [s for s in backup.get("sources", []) if s]
        if len(sources) == 1:
            chips.append(short_path(sources[0], 48))
        elif sources:
            names = [os.path.basename(os.path.normpath(s)) or s for s in sources]
            shown = ", ".join(names[:2])
            if len(names) > 2:
                shown += " +" + str(len(names) - 2)
            chips.append(f"{plural(len(sources), 'source', 'sources', 'sources5')}: {shown}")
        return "  ·  ".join(chips) if chips else i18n.t(
            "This backup has no sources. Open settings and add a folder or file.")

    def _target_line(self, backup):
        if core.cloud_provider(backup) == "none" and not backup.get("destination"):
            return i18n.t("No destination chosen.")
        target = short_path(core.display_target(backup), 66)
        last = backup.get("last_run") or {}
        parts = [f"→  {target}"]
        if last.get("ok") and last.get("bytes"):
            parts.append(core.human_size(last.get("bytes")))
        return "  ·  ".join(parts)

    def _new_backup(self):
        BackupDialog(self)

    def _edit_backup(self, backup_id):
        backup = core.get_backup(self.state, backup_id)
        if backup:
            BackupDialog(self, backup)

    def _save_backup(self, backup):
        core.put_backup(self.state, backup)
        core.save_state(self.state)
        self.detection = appdata_detect.detect()
        self._refresh_list()

    def _start_all(self):
        if self._running_id or self._batch_queue:
            self._stop_batch()
            return
        ids = [b["id"] for b in self.state.get("backups", [])]
        if not ids:
            return
        self._batch_queue = ids[1:]
        self._batch_total = len(ids)
        self._batch_ok = 0
        self._batch_errors = 0
        self._refresh_list()
        self._start_run(ids[0], from_batch=True)

    def _stop_batch(self):
        self._batch_queue = []
        self._cancel_flag.set()
        self._set_status(i18n.t("Stopping…"), WARN_TEXT)

    def _batch_next(self):
        if not self._batch_queue:
            if self._batch_total:
                summary = f"{i18n.t('Series finished')} — {self._batch_ok} OK"
                if self._batch_errors:
                    summary += ", " + plural(self._batch_errors, "error1", "errors", "errors5")
                self._set_status(summary, OK_TEXT if not self._batch_errors else WARN_TEXT)
                self._batch_total = 0
                self._refresh_list()
            return
        self.root.after(300, lambda: self._start_run(self._batch_queue.pop(0),
                                                     from_batch=True))

    def _start_run(self, backup_id, from_batch=False):
        if self._running_id:
            return
        backup = core.get_backup(self.state, backup_id)
        if not backup:
            return
        error = core.validate_backup(backup, self.state)
        if error:
            if from_batch:
                self._batch_errors += 1
                self._set_status(f"{i18n.t('Skipped')} “{backup.get('name', '')}”: {error}",
                                 WARN_TEXT)
                self._batch_next()
                return
            messagebox.showerror(i18n.t("Could not start the backup"), error,
                                 parent=self.root)
            return

        self._running_id = backup_id
        self._cancel_flag.clear()
        self._refresh_list()
        self._show_progress(backup_id, 0, 0, i18n.t("Preparing…"))
        if self._batch_total:
            done = self._batch_ok + self._batch_errors
            self._set_status(f"{i18n.t('Series')} {done + 1}/{self._batch_total}"
                             f" — “{backup['name']}”", MUTED)
        else:
            self._set_status(f"“{backup['name']}” — {i18n.t('Copying…')}", MUTED)

        snapshot = dict(backup, sources=list(backup.get("sources") or []))
        self._worker = threading.Thread(target=self._run_worker, args=(snapshot,),
                                        daemon=True)
        self._worker.start()

    def _toggle_run(self, backup_id):
        if backup_id == self._running_id:
            self._cancel_flag.set()
            self._set_status(i18n.t("Stopping the run…"), WARN_TEXT)

    def _run_worker(self, backup):
        def progress(done, total, label):
            self._queue.put(("progress", (backup["id"], done, total, label)))

        result = core.run_backup(backup, progress=progress,
                                 cancelled=self._cancel_flag.is_set)
        self._queue.put(("done", (backup["id"], result)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "progress":
                    self._show_progress(*payload)
                elif kind == "done":
                    self._finish(*payload)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    def _show_progress(self, backup_id, done, total, label):
        if not self.progress_row or not self.progress_row.winfo_manager():
            if self.progress_row:
                self.progress_row.pack(fill="x", before=self.status)
            else:
                return

        if total <= 0:
            if str(self.progress_bar.cget("mode")) != "indeterminate":
                self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            self.lbl_progress.configure(text="")
            text = label or i18n.t("Scanning files…")
        elif (label or "").startswith("upload:"):
            percent = int((label or "upload:0").split(":", 1)[1] or 0)
            if str(self.progress_bar.cget("mode")) != "determinate":
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(max(0.0, min(1.0, percent / 100)))
            self.lbl_progress.configure(text=f"{percent}%")
            text = f"{i18n.t('Uploading to cloud…')}  {percent}%"
        else:
            if str(self.progress_bar.cget("mode")) != "determinate":
                self.progress_bar.stop()
                self.progress_bar.configure(mode="determinate")
            self.progress_bar.set(min(1.0, done / total) if total else 0)
            self.lbl_progress.configure(text=f"{done} / {total}")
            short = os.path.basename(label or "")
            text = f"{i18n.t('Copying…')}  {done} / {total}"
            if short:
                text += f"  ·  {short}"

        if self._running_id:
            self._set_status(text, MUTED)
        card_label = self._detail_labels.get(backup_id)
        if card_label is not None:
            try:
                card_label.configure(text=text, text_color=ACCENT)
            except Exception:
                pass

    def _hide_progress(self):
        self.progress_bar.stop()
        if self.progress_row and self.progress_row.winfo_manager():
            self.progress_row.pack_forget()

    def _finish(self, backup_id, result):
        in_batch = bool(self._batch_total)
        backup = core.get_backup(self.state, backup_id)
        name = backup.get("name", "") if backup else ""
        if backup:
            core.apply_result(backup, result)
            core.save_state(self.state)

        self._running_id = None
        self._cancel_flag.clear()
        self._hide_progress()
        self._refresh_list()

        if result.get("ok"):
            details = [plural(result.get("files", 0), "file", "files", "files5"),
                       core.human_size(result.get("bytes", 0)),
                       f"{str(result.get('seconds', 0)).replace('.', ',')} s"]
            self._set_status(f"{i18n.t('Done')} — “{name}”: " + " · ".join(details)
                             + f"  →  {result.get('target', '')}", OK_TEXT)
        elif result.get("cancelled"):
            self._set_status(f"{i18n.t('Stopped')} — “{name}”.", WARN_TEXT)
        else:
            self._set_status(f"{i18n.t('Error')} — “{name}”: {result.get('message', '')}",
                             ERR_TEXT)

        if in_batch:
            if result.get("ok"):
                self._batch_ok += 1
            elif not result.get("cancelled"):
                self._batch_errors += 1
            if result.get("cancelled"):
                self._batch_queue = []
                self._batch_total = 0
                self._set_status(i18n.t("Series stopped."), WARN_TEXT)
                return
            self._batch_next()

    def _set_status(self, text, color=SUBTLE):
        self.status.configure(text=text, text_color=color)

    def _on_close(self):
        if self._running_id and not messagebox.askyesno(
                APP_NAME, i18n.t("Copying is in progress. Close the app?"),
                parent=self.root):
            return
        self._cancel_flag.set()
        try:
            cloud.kill_active()
        except Exception:
            pass
        self.root.destroy()

class BackupDialog(ctk.CTkToplevel):
    def __init__(self, app, backup=None):
        super().__init__(app.root)
        self.app = app
        self.existing = backup is not None
        self.backup = dict(backup) if backup else core.new_backup()
        self.backup["sources"] = list(self.backup.get("sources") or [])
        self.detection = appdata_detect.detect()
        self.backup["app_data"] = core.normalize_app_data(self.backup.get("app_data"))
        if not self.existing:
            inventory = self.detection.get("hermes") or {}
            self.backup["app_data"]["memory"] = inventory.get("preferred_memory", "builtin")
        if self.existing:
            self._zip_pref = bool(self.backup.get("use_zip", False))
        else:
            self._zip_pref = False
            self.backup["use_zip"] = False
        self._zip_pref_local = self._zip_pref
        self._provider = core.normalize_cloud(self.backup.get("cloud"))["provider"]
        self._picking = False
        self._last_pick = 0.0
        self._cloud_queue = queue.Queue()
        self._connecting = False
        if not self.backup.get("destination"):
            self.backup["destination"] = os.path.join(os.path.expanduser("~"), "BackupTool")

        self.title(i18n.t("Backup settings") if self.existing else i18n.t("New backup"))
        self.geometry(self._centered(720, 900))
        self.configure(fg_color=BG)
        self.transient(app.root)
        self.resizable(False, False)

        self._build()
        self._sync_sources()
        self._sync_app_data()
        self._sync_cloud()
        self._fit()
        self.after(200, self._poll_cloud)

        self.grab_set()
        self.after(120, lambda: enable_dark_titlebar(self))
        self.after(180, self._front)

    def _centered(self, width, height):
        self.update_idletasks()
        parent = self.app.root
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def _fit(self):
        try:
            self.update_idletasks()
            needed = self.body.winfo_reqheight() + 150
            height = min(max(620, needed), self.winfo_screenheight() - 100, 1250)
            self.geometry(self._centered(720, int(height)))
        except Exception:
            pass

    def _front(self):
        try:
            self.lift()
            self.focus_force()
            self.entry_name.focus_set()
        except Exception:
            pass

    def _build(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(18, 2))
        ctk.CTkLabel(head, text=self.title(), font=F_PANEL, text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(head, text=i18n.t("Name the copy, choose what to save and where."),
                     font=F_MUTED, text_color=MUTED).pack(anchor="w", pady=(2, 0))

        self._build_footer()

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                           scrollbar_button_color=BORDER,
                                           scrollbar_button_hover_color=SUBTLE)
        self.body.pack(fill="both", expand=True, padx=(16, 8), pady=(4, 0))
        body = self.body

        ctk.CTkLabel(body, text=i18n.t("NAME"), font=F_MUTED, text_color=SUBTLE).pack(
            anchor="w", padx=6, pady=(12, 4))
        self.entry_name = ctk.CTkEntry(
            body, height=38, corner_radius=9, fg_color=CARD_SEL, border_color=BORDER,
            border_width=1, text_color=TEXT, font=F_TEXT,
            placeholder_text=i18n.t("e.g. Photos"))
        self.entry_name.pack(fill="x", padx=6)
        self.entry_name.insert(0, self.backup.get("name", ""))
        self.entry_name.bind("<KeyRelease>", lambda _e: self._sync_preview())

        src_head = ctk.CTkFrame(body, fg_color="transparent")
        src_head.pack(fill="x", padx=6, pady=(14, 4))
        ctk.CTkLabel(src_head, text=i18n.t("SOURCES"), font=F_MUTED,
                     text_color=SUBTLE).pack(side="left")
        make_button(src_head, i18n.t("+  Folder"), self._add_folder, width=112, height=32,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                    corner_radius=9, font=("Segoe UI", 12, "bold")).pack(side="right")
        make_button(src_head, i18n.t("+  File"), self._add_file, width=112, height=32,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                    corner_radius=9, font=("Segoe UI", 12, "bold")).pack(
            side="right", padx=(0, 8))

        self.src_list = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        self.src_list.pack(fill="x", padx=6)

        self._build_appdata()

        zip_box = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        zip_box.pack(fill="x", padx=6, pady=(6, 0))
        zip_row = ctk.CTkFrame(zip_box, fg_color="transparent")
        zip_row.pack(fill="x", padx=14, pady=(12, 0))
        self.zip_switch = ctk.CTkSwitch(
            zip_row, text=i18n.t("Pack into a .zip archive"), font=F_SMALL,
            text_color=TEXT, progress_color=ACCENT, button_color="#ffffff",
            button_hover_color="#e6e8ec", fg_color=BORDER, width=44,
            command=self._on_zip_toggle)
        self.zip_switch.pack(side="left")
        if self._zip_pref:
            self.zip_switch.select()
        else:
            self.zip_switch.deselect()
        self.lbl_zip_lock = ctk.CTkLabel(zip_row, text="", font=F_MUTED,
                                         text_color=ERR_TEXT)
        self.lbl_zip_lock.pack(side="left", padx=(10, 0))
        self.lbl_zip_hint = ctk.CTkLabel(zip_box, text="", font=F_MUTED,
                                         text_color=MUTED, anchor="w", justify="left",
                                         wraplength=548)
        self.lbl_zip_hint.pack(fill="x", padx=14, pady=(2, 12))

        self._build_destination(body)
        self.lbl_preview = ctk.CTkLabel(body, text="", font=F_MUTED, text_color=MUTED,
                                        anchor="w", justify="left", wraplength=560)
        self.lbl_preview.pack(fill="x", padx=6, pady=(6, 0))
        self.lbl_error = ctk.CTkLabel(body, text="", font=F_SMALL, text_color=ERR_TEXT,
                                      anchor="w", justify="left", wraplength=560)
        self.lbl_error.pack(fill="x", padx=6, pady=(6, 4))

        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=24, pady=(8, 18))
        if self.existing:
            make_button(footer, i18n.t("Delete backup"), self._delete, width=132,
                        height=38, fg_color="transparent", hover_color=DANGER_SOFT,
                        text_color=ERR_TEXT, border_width=1, border_color=DANGER,
                        corner_radius=9, font=F_SMALL).pack(side="left")
        make_button(footer, i18n.t("Save"), self._save, width=120, height=40,
                    fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=ON_ACCENT,
                    corner_radius=9, font=F_BUTTON).pack(side="right")
        make_button(footer, i18n.t("Cancel"), self._cancel, width=100, height=40,
                    fg_color="transparent", hover_color=CARD_SEL, text_color=MUTED,
                    border_width=1, border_color=BORDER, corner_radius=9,
                    font=F_SMALL).pack(side="right", padx=(0, 8))

    def _build_appdata(self):
        detected = bool(self.detection.get("hermes")
                        or (self.detection.get("obsidian") or {}).get("vaults"))
        if not detected and not core.app_data_enabled(self.backup):
            self.appdata_open = False
            self.appdata_header = ctk.CTkFrame(self.body, fg_color="transparent")
            self.appdata_box = ctk.CTkFrame(self.body, fg_color="transparent")
            for name in ("sw_hermes", "badge_hermes", "lbl_hermes_path", "btn_mem_mnemo",
                         "btn_mem_builtin", "sw_obsidian", "badge_obsidian",
                         "lbl_obsidian_path", "btn_appdata"):
                setattr(self, name, None)
            return
        self.appdata_open = bool(core.app_data_enabled(self.backup))
        self.appdata_header = ctk.CTkFrame(self.body, fg_color="transparent")
        self.appdata_header.pack(fill="x", padx=6, pady=(14, 0))
        self.btn_appdata = make_button(
            self.appdata_header, self._appdata_label(), self._toggle_appdata,
            width=460, height=30, fg_color="transparent", hover_color=CARD_SEL,
            text_color=MUTED, anchor="w", corner_radius=8, font=F_SMALL)
        self.btn_appdata.pack(side="left")

        self.appdata_box = ctk.CTkFrame(self.body, fg_color=CARD, corner_radius=10)
        if self.appdata_open:
            self.appdata_box.pack(fill="x", padx=6, pady=(4, 0),
                                  after=self.appdata_header)
        box = self.appdata_box

        ctk.CTkLabel(box, text=i18n.t("Only Hermes and Obsidian are supported. "
                                      "Not using them? Keep this section folded."),
                     font=F_MUTED, text_color=INFO_TEXT, anchor="w", justify="left",
                     wraplength=520).pack(fill="x", padx=14, pady=(10, 0))

        hermes_row = ctk.CTkFrame(box, fg_color="transparent")
        hermes_row.pack(fill="x", padx=14, pady=(8, 0))
        self.sw_hermes = ctk.CTkSwitch(
            hermes_row, text="Hermes", font=F_TEXT, text_color=TEXT,
            progress_color=ACCENT, button_color="#ffffff",
            button_hover_color="#e6e8ec", fg_color=BORDER, width=44,
            command=self._on_hermes_toggle)
        self.sw_hermes.pack(side="left")
        self.badge_hermes = ctk.CTkLabel(hermes_row, text="", font=F_MUTED,
                                         corner_radius=6, height=20, padx=8,
                                         text_color=MUTED, fg_color=CARD_SEL)
        self.badge_hermes.pack(side="left", padx=(10, 0))
        self.lbl_hermes_path = ctk.CTkLabel(box, text="", font=F_MUTED,
                                            text_color=SUBTLE, anchor="w", justify="left",
                                            wraplength=560)
        self.lbl_hermes_path.pack(fill="x", padx=14, pady=(2, 0))

        memory_row = ctk.CTkFrame(box, fg_color="transparent")
        memory_row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(memory_row, text=i18n.t("Memory:"), font=F_SMALL,
                     text_color=MUTED).pack(side="left")
        self.btn_mem_mnemo = make_button(
            memory_row, "Mnemosyne", lambda: self._pick_memory("mnemosyne"),
            width=104, height=28, fg_color=CARD_SEL, hover_color=BORDER,
            text_color=TEXT, border_width=1, border_color=BORDER,
            corner_radius=8, font=F_MUTED)
        self.btn_mem_mnemo.pack(side="left", padx=(10, 6))
        self.btn_mem_builtin = make_button(
            memory_row, i18n.t("Built-in"), lambda: self._pick_memory("builtin"),
            width=104, height=28, fg_color=CARD_SEL, hover_color=BORDER,
            text_color=TEXT, border_width=1, border_color=BORDER,
            corner_radius=8, font=F_MUTED)
        self.btn_mem_builtin.pack(side="left")

        obsidian_row = ctk.CTkFrame(box, fg_color="transparent")
        obsidian_row.pack(fill="x", padx=14, pady=(10, 0))
        self.sw_obsidian = ctk.CTkSwitch(
            obsidian_row, text="Obsidian", font=F_TEXT, text_color=TEXT,
            progress_color=ACCENT, button_color="#ffffff",
            button_hover_color="#e6e8ec", fg_color=BORDER, width=44,
            command=self._on_obsidian_toggle)
        self.sw_obsidian.pack(side="left")
        self.badge_obsidian = ctk.CTkLabel(obsidian_row, text="", font=F_MUTED,
                                           corner_radius=6, height=20, padx=8,
                                           text_color=MUTED, fg_color=CARD_SEL)
        self.badge_obsidian.pack(side="left", padx=(10, 0))
        self.lbl_obsidian_path = ctk.CTkLabel(box, text="", font=F_MUTED,
                                              text_color=SUBTLE, anchor="w",
                                              justify="left", wraplength=560)
        self.lbl_obsidian_path.pack(fill="x", padx=14, pady=(2, 0))

        ctk.CTkLabel(box, text=i18n.t("Files of these apps are taken automatically — "
                                      "you do not need to add them as sources."),
                     font=F_MUTED, text_color=SUBTLE, anchor="w", justify="left",
                     wraplength=560).pack(fill="x", padx=14, pady=(8, 12))

    def _build_destination(self, body):
        ctk.CTkLabel(body, text=i18n.t("DESTINATION"), font=F_MUTED,
                     text_color=SUBTLE).pack(anchor="w", padx=6, pady=(10, 4))

        provider_row = ctk.CTkFrame(body, fg_color="transparent")
        provider_row.pack(fill="x", padx=6)
        self.provider_buttons = {}
        for provider, label in (("none", i18n.t("Local")),
                                ("dropbox", "Dropbox"), ("gdrive", "Google Drive")):
            button = make_button(provider_row, label,
                                 lambda value=provider: self._set_provider(value),
                                 width=132, height=32, fg_color=CARD_SEL,
                                 hover_color=BORDER, text_color=TEXT,
                                 border_width=1, border_color=BORDER,
                                 corner_radius=8, font=F_SMALL)
            button.pack(side="left", padx=(0, 6))
            self.provider_buttons[provider] = button

        self.local_row = ctk.CTkFrame(body, fg_color="transparent")
        self.local_row.pack(fill="x", padx=6, pady=(8, 0))
        self.entry_dest = ctk.CTkEntry(
            self.local_row, height=38, corner_radius=9, fg_color=CARD_SEL,
            border_color=BORDER, border_width=1, text_color=TEXT, font=F_TEXT)
        self.entry_dest.pack(side="left", fill="x", expand=True)
        self.entry_dest.insert(0, self.backup.get("destination", ""))
        self.entry_dest.bind("<KeyRelease>", lambda _e: self._sync_preview())
        make_button(self.local_row, i18n.t("Browse…"), self._pick_destination,
                    width=92, height=38, fg_color=CARD_SEL, hover_color=BORDER,
                    text_color=TEXT, corner_radius=9,
                    font=F_SMALL).pack(side="left", padx=(8, 0))

        self.cloud_box = ctk.CTkFrame(body, fg_color=CARD, corner_radius=10)
        cloud_head = ctk.CTkFrame(self.cloud_box, fg_color="transparent")
        cloud_head.pack(fill="x", padx=14, pady=(10, 0))
        self.badge_cloud = ctk.CTkLabel(cloud_head, text="", font=F_MUTED,
                                        corner_radius=6, height=20, padx=8,
                                        text_color=MUTED, fg_color=CARD_SEL)
        self.badge_cloud.pack(side="left")
        self.btn_cloud_connect = make_button(cloud_head, i18n.t("Connect"),
                                             self._connect_cloud, width=104, height=28,
                                             fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                             text_color=ON_ACCENT, corner_radius=8,
                                             font=F_SMALL)
        self.btn_cloud_connect.pack(side="right")
        self.btn_cloud_forget = make_button(cloud_head, i18n.t("Disconnect"),
                                            self._disconnect_cloud, width=96, height=28,
                                            fg_color="transparent",
                                            hover_color=DANGER_SOFT, text_color=ERR_TEXT,
                                            border_width=1, border_color=DANGER,
                                            corner_radius=8, font=F_MUTED)

        self.lbl_cloud_status = ctk.CTkLabel(self.cloud_box, text="", font=F_MUTED,
                                             text_color=MUTED, anchor="w",
                                             justify="left", wraplength=540)
        self.lbl_cloud_status.pack(fill="x", padx=14, pady=(2, 0))
        self.lbl_cloud_info = ctk.CTkLabel(self.cloud_box, text="", font=F_MUTED,
                                           text_color=SUBTLE, anchor="w",
                                           justify="left", wraplength=560)
        self.lbl_cloud_info.pack(fill="x", padx=14, pady=(4, 0))

        remote_row = ctk.CTkFrame(self.cloud_box, fg_color="transparent")
        remote_row.pack(fill="x", padx=14, pady=(8, 0))
        ctk.CTkLabel(remote_row, text=i18n.t("Cloud folder:"), font=F_SMALL,
                     text_color=SUBTLE).pack(side="left")
        self.entry_remote = ctk.CTkEntry(
            remote_row, height=34, corner_radius=8, fg_color=CARD_SEL,
            border_color=BORDER, border_width=1, text_color=TEXT, font=F_TEXT,
            placeholder_text=i18n.t("empty = cloud root"))
        self.entry_remote.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.entry_remote.insert(0, core.normalize_cloud(self.backup.get("cloud"))["path"])
        self.entry_remote.bind("<KeyRelease>", lambda _e: self._sync_preview())

        self.google_box = ctk.CTkFrame(self.cloud_box, fg_color="transparent")
        google_head = ctk.CTkFrame(self.google_box, fg_color="transparent")
        google_head.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(google_head, text=i18n.t("Own client ID required"), font=F_SMALL,
                     text_color=SUBTLE).pack(side="left")
        make_button(google_head, i18n.t("How to get it?"), self._show_google_help,
                    width=140, height=26, fg_color="transparent", hover_color=CARD_SEL,
                    text_color=ACCENT, border_width=1, border_color=ACCENT,
                    corner_radius=8, font=F_MUTED).pack(side="right")
        self.entry_client_id = ctk.CTkEntry(
            self.google_box, height=34, corner_radius=8, fg_color=CARD_SEL,
            border_color=BORDER, border_width=1, text_color=TEXT, font=F_SMALL,
            placeholder_text="Client ID (…apps.googleusercontent.com)")
        self.entry_client_id.pack(fill="x")
        self.entry_client_secret = ctk.CTkEntry(
            self.google_box, height=34, corner_radius=8, fg_color=CARD_SEL,
            border_color=BORDER, border_width=1, text_color=TEXT, font=F_SMALL,
            placeholder_text="Client secret")
        self.entry_client_secret.pack(fill="x", pady=(6, 0))

    def _appdata_label(self):
        chevron = "▾" if getattr(self, "appdata_open", False) else "▸"
        return f"{chevron}   {i18n.t('Data from apps')} (Hermes, Obsidian)"

    def _toggle_appdata(self):
        self.appdata_open = not self.appdata_open
        self.btn_appdata.configure(text=self._appdata_label())
        if self.appdata_open:
            self.appdata_box.pack(fill="x", padx=6, pady=(4, 0),
                                  after=self.appdata_header)
        else:
            self.appdata_box.pack_forget()
        self._fit()

    def _on_hermes_toggle(self):
        self.backup["app_data"]["hermes"] = bool(self.sw_hermes.get())
        self._sync_app_data()

    def _on_obsidian_toggle(self):
        self.backup["app_data"]["obsidian"] = bool(self.sw_obsidian.get())
        self._sync_app_data()

    def _pick_memory(self, mode):
        if mode in core.MEMORY_MODES:
            self.backup["app_data"]["memory"] = mode
            self._sync_app_data()

    def _sync_app_data(self):
        if getattr(self, "sw_hermes", None) is None:
            self._sync_zip()
            return
        data = self.backup["app_data"]
        hermes = self.detection.get("hermes")

        if hermes:
            self.sw_hermes.configure(state="normal")
            (self.sw_hermes.select if data["hermes"] else self.sw_hermes.deselect)()
            self.badge_hermes.configure(text=i18n.t("detected"), fg_color=OK_BG,
                                        text_color=OK_TEXT)
            self.lbl_hermes_path.configure(text=short_path(hermes["root"], 64),
                                           text_color=SUBTLE)
        else:
            data["hermes"] = False
            self.sw_hermes.deselect()
            self.sw_hermes.configure(state="disabled")
            self.badge_hermes.configure(text=i18n.t("not detected"), fg_color=CARD_SEL,
                                        text_color=SUBTLE)
            self.lbl_hermes_path.configure(
                text=i18n.t("Hermes data not found on this computer."),
                text_color=SUBTLE)

        modes = {"mnemosyne": bool(hermes and hermes.get("mnemosyne_available")),
                 "builtin": bool(hermes and hermes.get("builtin_available"))}
        if hermes and not (modes["mnemosyne"] or modes["builtin"]):
            modes[data["memory"]] = True
        if hermes and not modes.get(data["memory"]):
            data["memory"] = "mnemosyne" if modes["mnemosyne"] else "builtin"

        for mode, button, label in (("mnemosyne", self.btn_mem_mnemo, "Mnemosyne"),
                                    ("builtin", self.btn_mem_builtin, i18n.t("Built-in"))):
            available = modes[mode]
            active = available and data["memory"] == mode
            button.configure(text=label if available else label + " " + i18n.t("(none)"))
            if available and data["hermes"]:
                button.configure(state="normal",
                                 fg_color=ACCENT if active else CARD_SEL,
                                 hover_color=ACCENT_HOVER if active else BORDER,
                                 text_color=ON_ACCENT if active else TEXT,
                                 border_color=ACCENT if active else BORDER)
            else:
                button.configure(state="disabled", fg_color=CARD_SEL,
                                 text_color=SUBTLE, border_color=BORDER)

        vaults = (self.detection.get("obsidian") or {}).get("vaults") or []
        if vaults:
            self.sw_obsidian.configure(state="normal")
            (self.sw_obsidian.select if data["obsidian"] else self.sw_obsidian.deselect)()
            self.badge_obsidian.configure(text=i18n.t("detected"), fg_color=OK_BG,
                                          text_color=OK_TEXT)
            names = [os.path.basename(v.rstrip("\\/")) or v for v in vaults]
            text = plural(len(vaults), "vault", "vaults", "vaults5") + ": " + \
                ", ".join(names[:3])
            if len(names) > 3:
                text += " +" + str(len(names) - 3)
            self.lbl_obsidian_path.configure(text=short_path(text, 88),
                                             text_color=SUBTLE)
        else:
            data["obsidian"] = False
            self.sw_obsidian.deselect()
            self.sw_obsidian.configure(state="disabled")
            self.badge_obsidian.configure(text=i18n.t("not detected"), fg_color=CARD_SEL,
                                          text_color=SUBTLE)
            self.lbl_obsidian_path.configure(
                text=i18n.t("Obsidian vaults not found on this computer."),
                text_color=SUBTLE)

        self._sync_zip()

    def _ask_folder(self, title, initial=None):
        now = time.monotonic()
        if self._picking or now - self._last_pick < 0.35:
            return None
        self._picking = True
        try:
            if initial and os.path.isdir(initial):
                return filedialog.askdirectory(parent=self, title=title,
                                               initialdir=initial)
            return filedialog.askdirectory(parent=self, title=title)
        finally:
            self._picking = False
            self._last_pick = time.monotonic()

    def _ask_files(self, title):
        now = time.monotonic()
        if self._picking or now - self._last_pick < 0.35:
            return ()
        self._picking = True
        try:
            return filedialog.askopenfilenames(parent=self, title=title) or ()
        finally:
            self._picking = False
            self._last_pick = time.monotonic()

    def _add_folder(self):
        path = self._ask_folder(i18n.t("Choose a folder to back up"))
        if path:
            self._append_source(os.path.normpath(path))

    def _add_file(self):
        for path in self._ask_files(i18n.t("Choose files to back up")):
            self._append_source(os.path.normpath(path))

    def _append_source(self, path):
        if not path:
            return
        if path in self.backup["sources"]:
            self._set_error(i18n.t("This source is already on the list."))
            return
        self.backup["sources"].append(path)
        self._set_error("")
        if not self.entry_name.get().strip():
            base = os.path.basename(path.rstrip("\\/"))
            self.entry_name.delete(0, "end")
            self.entry_name.insert(0, os.path.splitext(base)[0]
                                   if os.path.isfile(path) else base)
        self._sync_sources()
        self._sync_zip()

    def _remove_source(self, path):
        self.backup["sources"] = [s for s in self.backup["sources"] if s != path]
        self._sync_sources()
        self._sync_zip()

    def _sync_sources(self):
        for widget in self.src_list.winfo_children():
            widget.destroy()

        sources = self.backup["sources"]
        if sources:
            if not self.src_list.winfo_manager():
                if self.appdata_header.winfo_manager():
                    self.src_list.pack(fill="x", padx=6, before=self.appdata_header)
                else:
                    self.src_list.pack(fill="x", padx=6)
        else:
            self.src_list.pack_forget()

        for path in sources:
            row = ctk.CTkFrame(self.src_list, fg_color=CARD_SEL, corner_radius=8)
            row.pack(fill="x", pady=3, padx=2)
            exists = os.path.exists(path)
            kind = i18n.t("folder") if os.path.isdir(path) else i18n.t("file2")
            ctk.CTkLabel(row, text=kind, font=F_MUTED,
                         text_color=ACCENT if exists else SUBTLE, width=52,
                         anchor="w").pack(side="left", padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=path if exists else f"{path} {i18n.t('missing')}",
                         font=F_SMALL, text_color=TEXT if exists else ERR_TEXT,
                         anchor="w", justify="left", wraplength=450).pack(
                side="left", fill="x", expand=True, pady=8)
            make_button(row, "✕", lambda p=path: self._remove_source(p),
                        width=28, height=28, fg_color="transparent",
                        hover_color=DANGER_SOFT, text_color=MUTED,
                        corner_radius=6, font=F_SMALL).pack(side="right", padx=(4, 6))

        self.src_list.update_idletasks()
        self._fit()

    def _set_provider(self, provider):
        if provider == "none":
            self._zip_pref = self._zip_pref_local
        self._provider = provider
        data = core.normalize_cloud(self.backup.get("cloud"))
        data["provider"] = provider
        self.backup["cloud"] = data
        if provider != "none" and not self.entry_remote.get().strip() and data["path"]:
            self.entry_remote.insert(0, data["path"])
        self._sync_zip()
        self._sync_cloud()

    def _sync_cloud(self):
        provider = self._provider
        for value, button in self.provider_buttons.items():
            active = value == provider
            button.configure(fg_color=ACCENT if active else CARD_SEL,
                             text_color=ON_ACCENT if active else TEXT,
                             border_color=ACCENT if active else BORDER,
                             hover_color=ACCENT_HOVER if active else BORDER)

        if provider == "none":
            self.cloud_box.pack_forget()
            if not self.local_row.winfo_manager():
                self.local_row.pack(fill="x", padx=6, pady=(8, 0), before=self.lbl_preview)
            self._sync_preview()
            self._fit()
            return

        self.local_row.pack_forget()
        if not self.cloud_box.winfo_manager():
            self.cloud_box.pack(fill="x", padx=6, pady=(8, 0), before=self.lbl_preview)

        label = cloud.PROVIDER_LABELS.get(provider, provider)
        connected = cloud.remote_ready(provider)
        if connected:
            account = cloud.remote_account(provider)
            self.badge_cloud.configure(text=i18n.t("connected"), fg_color=OK_BG,
                                       text_color=OK_TEXT)
            self.lbl_cloud_status.configure(
                text=i18n.t("Account: {account}", account=account) if account
                else i18n.t("{provider} — account connected.", provider=label),
                text_color=MUTED)
            self.btn_cloud_connect.pack_forget()
            self.btn_cloud_forget.pack(side="right")
            self.google_box.pack_forget()
            self.lbl_cloud_info.configure(text="")
        else:
            self.badge_cloud.configure(text=i18n.t("not connected"), fg_color=CARD_SEL,
                                       text_color=SUBTLE)
            self.lbl_cloud_status.configure(
                text=i18n.t("Sign in to {provider} in your browser (no API keys).",
                            provider=label), text_color=MUTED)
            self.btn_cloud_forget.pack_forget()
            if not self.btn_cloud_connect.winfo_manager():
                self.btn_cloud_connect.pack(side="right")
            info = i18n.t("On first connection rclone is downloaded (~32 MB) and the "
                          "browser opens for sign-in. The token stays on this computer "
                          "only — it is never part of a backup.")
            if provider == "gdrive":
                info += " " + i18n.t("Google also needs your own client ID — the "
                                     "step-by-step guide is behind “How to get it?”.")
            self.lbl_cloud_info.configure(text=info, text_color=SUBTLE)
            if provider == "gdrive":
                if not self.google_box.winfo_manager():
                    self.google_box.pack(fill="x", padx=14, pady=(8, 0))
            else:
                self.google_box.pack_forget()

        self._sync_preview()
        self._fit()

    def _connect_cloud(self):
        if self._connecting or self._provider == "none":
            return
        provider = self._provider
        client_id = self.entry_client_id.get().strip()
        secret = self.entry_client_secret.get().strip()
        if provider == "gdrive" and not client_id:
            self._set_error(i18n.t("Paste the Client ID from Google Cloud (hint above)."))
            return
        self._connecting = True
        self._set_error("")
        self.btn_cloud_connect.pack(side="right")
        self.btn_cloud_connect.configure(state="disabled", text=i18n.t("Connecting…"))
        self.badge_cloud.configure(text=i18n.t("connecting…"), fg_color=CARD_SEL,
                                   text_color=ACCENT)
        threading.Thread(target=self._connect_worker,
                         args=(provider, client_id, secret), daemon=True).start()

    def _connect_worker(self, provider, client_id, secret):
        def status(text):
            self._cloud_queue.put(("status", text))

        try:
            cloud.authorize(provider, client_id, secret, on_status=status)
            self._cloud_queue.put(("done", ""))
        except Exception as exc:
            self._cloud_queue.put(("error", str(exc)))

    def _poll_cloud(self):
        try:
            while True:
                kind, payload = self._cloud_queue.get_nowait()
                if kind == "status":
                    self.lbl_cloud_status.configure(text=payload, text_color=ACCENT)
                elif kind in ("done", "error"):
                    self._connecting = False
                    self.btn_cloud_connect.configure(state="normal",
                                                     text=i18n.t("Connect"))
                    self._sync_cloud()
                    if kind == "error":
                        self._set_error(payload)
        except queue.Empty:
            pass
        try:
            self.after(200, self._poll_cloud)
        except Exception:
            pass

    def _disconnect_cloud(self):
        provider = self._provider
        if provider == "none":
            return
        label = cloud.PROVIDER_LABELS.get(provider, provider)
        if not messagebox.askyesno(
                i18n.t("Disconnect account?"),
                i18n.t("Disconnect {provider}? The backup stays on disk — you will "
                       "need to sign in again to upload to the cloud.", provider=label),
                parent=self):
            return
        cloud.forget(provider)
        self._sync_cloud()

    def _show_google_help(self):
        GoogleHelpDialog(self, on_open=self._open_url)

    def _open_url(self, url):
        try:
            os.startfile(url)
        except Exception:
            pass

    def _on_zip_toggle(self):
        self._zip_pref = bool(self.zip_switch.get())
        if self._provider == "none":
            self._zip_pref_local = self._zip_pref
        self._sync_zip()

    def _sync_zip(self):
        sources = self.backup["sources"]
        if self._provider != "none":
            self.backup["use_zip"] = True
            self.zip_switch.pack_forget()
            self.lbl_zip_lock.configure(text=i18n.t("🔒   ZIP — required for cloud"),
                                        text_color=ERR_TEXT)
            self.lbl_zip_hint.configure(
                text=i18n.t("In the cloud a backup is always a single ZIP file. "
                            "Uploading a folder means thousands of separate files, "
                            "which API limits slow down heavily."), text_color=MUTED)
            self._sync_preview()
            return

        if not self.zip_switch.winfo_manager():
            self.zip_switch.pack(side="left", before=self.lbl_zip_lock)
        self.lbl_zip_lock.configure(text="")

        has_content = bool(sources) or core.app_data_enabled(self.backup)
        available = core.zip_available_for(self.backup)
        if available:
            self.zip_switch.configure(state="normal")
            self.backup["use_zip"] = self._zip_pref
        else:
            self.zip_switch.configure(state="disabled")
            self.backup["use_zip"] = False
        show_on = self._zip_pref if (available or not has_content) else False
        (self.zip_switch.select if show_on else self.zip_switch.deselect)()

        if not has_content:
            hint = i18n.t("Add a source or enable app data to choose the backup type.")
        elif not available:
            hint = i18n.t("Sources are already archives (.zip, .rar, .7z…). "
                          "They are stored unchanged.")
        elif self.backup.get("use_zip"):
            hint = i18n.t("Everything goes into a single .zip file, replaced on every run.")
        else:
            hint = i18n.t("Files are copied into the backup folder — existing ones "
                          "overwritten, new ones added.")
        self.lbl_zip_hint.configure(text=hint, text_color=MUTED)
        self._sync_preview()

    def _draft(self):
        draft = dict(self.backup)
        draft["name"] = self.entry_name.get().strip()
        draft["destination"] = self.entry_dest.get().strip()
        draft["sources"] = list(self.backup["sources"])
        draft["app_data"] = core.normalize_app_data(self.backup["app_data"])
        draft["cloud"] = {
            "provider": self._provider,
            "path": self.entry_remote.get().strip() if self._provider != "none" else "",
        }
        draft["use_zip"] = core.use_zip_for(draft)
        return draft

    def _sync_preview(self):
        draft = self._draft()
        if self._provider == "none" and not draft["destination"]:
            self.lbl_preview.configure(
                text=i18n.t("Choose the folder where copies are stored."),
                text_color=MUTED)
            return
        target = core.display_target(draft)
        kind = "ZIP" if draft["use_zip"] else i18n.t("folder")
        self.lbl_preview.configure(text=f"{i18n.t('Target:')}  {target}   ({kind})",
                                   text_color=MUTED)

    def _set_error(self, text):
        self.lbl_error.configure(text=text)

    def _pick_destination(self):
        current = self.entry_dest.get().strip()
        initial = current if os.path.isdir(current) else os.path.expanduser("~")
        path = self._ask_folder(i18n.t("Choose the destination folder"), initial=initial)
        if path:
            self.entry_dest.delete(0, "end")
            self.entry_dest.insert(0, os.path.normpath(path))
            self._sync_preview()

    def _save(self):
        draft = self._draft()
        error = core.validate_backup(draft, self.app.state, detection=self.detection)
        if error:
            self._set_error(error)
            return
        self._set_error("")
        self.backup.update(draft)
        self.app._save_backup(self.backup)
        self._close()

    def _delete(self):
        if not messagebox.askyesno(
                i18n.t("Delete this backup?"),
                i18n.t("Remove “{name}” from the list?\n\nFiles on disk stay where "
                       "they are — only the entry and its settings are removed.",
                       name=self.backup.get("name", "")),
                parent=self):
            return
        core.remove_backup(self.app.state, self.backup["id"])
        core.save_state(self.app.state)
        self.app._refresh_list()
        self.app._set_status(f"{i18n.t('Delete backup')} — “{self.backup.get('name', '')}”")
        self._close()

    def _cancel(self):
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

class GoogleHelpDialog(ctk.CTkToplevel):
    URL = "https://console.cloud.google.com/apis/credentials"

    def __init__(self, parent, on_open=None):
        super().__init__(parent)
        self.on_open = on_open
        self.title("Google Drive — client ID")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.transient(parent)
        self.geometry(self._placed(parent, 560, 470))

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=22, pady=(18, 6))
        ctk.CTkLabel(head, text=i18n.t("Own client ID in 5 minutes"), font=F_PANEL,
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(head, text=i18n.t("Free, one-time, no card and no API keys."),
                     font=F_MUTED, text_color=MUTED).pack(anchor="w", pady=(2, 0))

        body = ctk.CTkFrame(self, fg_color=CARD, corner_radius=10)
        body.pack(fill="both", expand=True, padx=22, pady=(4, 0))
        for step in (
            "Sign in to your Google account and create a project (any name).",
            "APIs & Services → Library → search “Google Drive API” → Enable.",
            "OAuth consent screen: External, app name, your e-mail, then Publish app "
            "(Testing mode expires tokens after 7 days).",
            "Credentials → Create credentials → OAuth client ID → Desktop app.",
            "Copy the Client ID and secret into the backup settings and click Connect.",
            "Google will warn about an unverified app — it is your own app, so click "
            "Advanced → Go to …",
        ):
            ctk.CTkLabel(body, text=i18n.t(step), font=F_SMALL, text_color=TEXT,
                         anchor="w", justify="left", wraplength=470).pack(
                fill="x", padx=14, pady=(8, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=22, pady=(12, 16))
        make_button(footer, i18n.t("Open Google console"), self._open, width=190,
                    height=36, fg_color=ACCENT, hover_color=ACCENT_HOVER,
                    text_color=ON_ACCENT, corner_radius=9,
                    font=F_SMALL).pack(side="left")
        make_button(footer, i18n.t("Close"), self.destroy, width=90, height=36,
                    fg_color="transparent", hover_color=CARD_SEL, text_color=MUTED,
                    border_width=1, border_color=BORDER, corner_radius=9,
                    font=F_SMALL).pack(side="right")

        self.grab_set()
        self.after(120, lambda: enable_dark_titlebar(self))
        self.after(160, self._front)

    def _placed(self, parent, width, height):
        parent.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
        return f"{width}x{height}+{x}+{y}"

    def _front(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _open(self):
        if self.on_open:
            self.on_open(self.URL)

def _install_excepthook():
    log_path = os.path.join(os.path.dirname(core.default_state_path()) or ".",
                            "error.log")

    def handler(exc_type, exc_value, exc_tb):
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"\n--- {core.now_iso()} ---\n")
                traceback.print_exception(exc_type, exc_value, exc_tb, file=handle)
        except Exception:
            pass
        try:
            messagebox.showerror(APP_NAME, f"{i18n.t('Unexpected error:')}\n{exc_value}")
        except Exception:
            pass

    sys.excepthook = handler

def main():
    _install_excepthook()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    BackupApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
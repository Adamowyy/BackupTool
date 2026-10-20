"""UI translations. English strings are the source; Polish lives here."""

LANGUAGES = ("pl", "en")
LABELS = {"pl": "PL", "en": "EN"}
DEFAULT_LANGUAGE = "en"

PL = {
    "BackupTool": "BackupTool",
    "Backups of folders and files — one click.": "Kopie zapasowe folderów i plików — jeden klik.",
    "+  New backup": "+  Nowy backup",
    "Your backups": "Twoje backupy",
    "▶   Run all": "▶   Uruchom wszystkie",
    "■   Stop": "■   Przerwij",
    "Save all": "Zapisz wszystko",
    "settings": "ustawienia",
    "Open settings": "Otwórz ustawienia",
    "Create your first backup": "Utwórz pierwszy backup",
    "No backups yet": "Nie masz jeszcze żadnego backupu",
    "Pick a folder or a file, name the copy and choose where it lives.":
        "Wybierz folder albo plik, nazwij kopię i wskaż, gdzie ma leżeć.",
    "Add your first backup to get started.": "Dodaj pierwszy backup, aby zacząć.",
    "Click Start to refresh a copy.": "Kliknij Start, aby zaktualizować kopię.",
    "New": "Nowy",
    "Running…": "Trwa…",
    "Stopped": "Przerwano",
    "today {time}": "dziś {time}",
    "yesterday {time}": "wczoraj {time}",
    "{days} days ago": "{days} dni temu",
    "Series": "Seria",
    "Start": "Start",
    "Stop": "Stop",
    "Stop the backup": "Zatrzymaj backup",
    "Uploading to cloud…": "Wysyłanie do chmury…",
    "Unexpected error:": "Nieoczekiwany błąd:",
    "Series finished": "Seria zakończona",
    "Error": "Błąd",
    "Ready": "Gotowe",
    "Needs setup": "Wymaga konfiguracji",
    "Set up": "Konfiguruj",
    "Drive {drive} is not available on this computer.":
        "Dysk {drive} nie jest dostępny na tym komputerze.",
    "Copied": "Skopiowano",
    "Preparing…": "Przygotowanie…",
    "Scanning files…": "Skanowanie plików…",
    "Copying…": "Kopiowanie…",
    "Uploading to cloud…": "Wysyłanie do chmury…",
    "Uploading files to the cloud…": "Wysyłam pliki do chmury…",
    "Stopping…": "Przerywanie…",
    "Stopping the run…": "Przerywanie kopiowania…",
    "This backup has no sources. Open settings and add a folder or file.":
        "Brak źródeł — otwórz ustawienia i dodaj folder lub plik.",
    "No destination chosen.": "Nie wybrano miejsca zapisu.",
    "Could not start the backup": "Nie można uruchomić backupu",
    "Done": "Gotowe",
    "Done and uploaded": "Gotowe i wysłane",
    "Stop anyway?": "Przerwać?",
    "Copying is in progress. Close the app?": "Trwa kopiowanie. Zamknąć aplikację?",
    "Unexpected error": "Nieoczekiwany error",
    "Unexpected error:": "Nieoczekiwany błąd:",
    "series": "seria",
    "Series finished": "Seria zakończona",
    "Series stopped.": "Przerwano serię.",
    "Skipped": "Pominięto",
    "backup": "backup",
    "backups": "backupy",
    "backups5": "backupów",
    "source": "źródło",
    "sources": "źródła",
    "sources5": "źródeł",
    "file": "plik",
    "files": "pliki",
    "files5": "plików",
    "vault": "sejf",
    "vaults": "sejfy",
    "vaults5": "sejfów",
    "error1": "błąd",
    "errors": "błędy",
    "errors5": "błędów",

    "Backup settings": "Ustawienia backupu",
    "Name the copy, choose what to save and where.":
        "Nazwij kopię, wybierz co zapisać i gdzie.",
    "NAME": "NAZWA",
    "e.g. Photos": "np. Zdjęcia",
    "SOURCES": "ŹRÓDŁA",
    "+  Folder": "+  Folder",
    "+  File": "+  Plik",
    "Nothing here yet — add a folder or a file.":
        "Nic tu jeszcze nie ma — dodaj folder lub plik.",
    "folder": "folder",
    "file2": "plik",
    "missing": "(missing)",
    "Data from apps": "Dane aplikacji",
    "Only Hermes and Obsidian are supported. Not using them? Keep this section folded.":
        "Obsługiwane są tylko Hermes i Obsidian. Nie używasz ich? Zostaw tę sekcję zwiniętą.",
    "detected": "wykryty",
    "not detected": "nie wykryty",
    "Hermes data not found on this computer.": "Nie znalazłem danych Hermesa na tym komputerze.",
    "Obsidian vaults not found on this computer.":
        "Nie znalazłem sejfów Obsidiana na tym komputerze.",
    "Memory:": "Pamięć:",
    "Built-in": "Wbudowana",
    "(none)": "(brak)",
    "Files of these apps are taken automatically — you do not need to add them as sources.":
        "Pliki tych aplikacji biorę automatycznie — nie musisz dodawać ich do źródeł.",
    "Pack into a .zip archive": "Spakuj do archiwum .zip",
    "Add a source or enable app data to choose the backup type.":
        "Dodaj źródło albo zaznacz dane aplikacji, aby wybrać typ backupu.",
    "Sources are already archives (.zip, .rar, .7z…). They are stored unchanged.":
        "Źródła to już archiwa (.zip, .rar, .7z…) — zostaną zapisane bez zmian.",
    "Everything goes into a single .zip file, replaced on every run.":
        "Wszystko trafi do jednego pliku .zip, nadpisywanego przy każdym uruchomieniu.",
    "Files are copied into the backup folder — existing ones overwritten, new ones added.":
        "Pliki zostaną skopiowane do folderu backupu — istniejące nadpisane, nowe dodane.",
    "🔒   ZIP — required for cloud": "🔒   ZIP — wymagane w chmurze",
    "In the cloud a backup is always a single ZIP file. Uploading a folder means "
    "thousands of separate files, which API limits slow down heavily.":
        "W chmurze kopia jest zawsze jednym plikiem ZIP. Wysyłanie folderu to tysiące "
        "osobnych plików, które limity API mocno spowalniają.",
    "DESTINATION": "MIEJSCE ZAPISU",
    "Local": "Lokalnie",
    "Browse…": "Zmień…",
    "connected": "połączone",
    "not connected": "nie połączone",
    "Connecting…": "Łączę…",
    "connecting…": "łączenie…",
    "Connect": "Połącz",
    "Disconnect": "Odłącz",
    "Sign in to {provider} in your browser (no API keys).":
        "Zaloguj się do {provider} w przeglądarce (bez kluczy API).",
    "On first connection rclone is downloaded (~32 MB) and the browser opens for sign-in. "
    "The token stays on this computer only — it is never part of a backup.":
        "Przy pierwszym połączeniu pobierze się rclone (~32 MB) i otworzy przeglądarka do "
        "logowania. Token zostaje tylko na tym komputerze — nie trafia do kopii.",
    "Google also needs your own client ID — the step-by-step guide is behind "
    "“How to get it?”.":
        "Google wymaga dodatkowo własnego client ID — opis krok po kroku znajdziesz pod "
        "przyciskiem „Jak to zdobyć?”.",
    "Cloud folder:": "Folder w chmurze:",
    "empty = cloud root": "puste = główny folder chmury",
    "Own client ID required": "Wymagany własny client ID",
    "How to get it?": "Jak to zdobyć?",
    "Account: {account}": "Konto: {account}",
    "{provider} — account connected.": "{provider} — konto połączone.",
    "Choose the folder where copies are stored.":
        "Wybierz folder, w którym mają leżeć kopie.",
    "Target:": "Zapis:",
    "Save": "Zapisz",
    "Cancel": "Anuluj",
    "Delete backup": "Usuń backup",
    "Delete this backup?": "Usunąć backup?",
    "Remove “{name}” from the list?\n\nFiles on disk stay where they are — only the "
    "entry and its settings are removed.":
        "Usunąć backup „{name}” z listy?\n\nPliki na dysku zostaną — zniknie tylko wpis "
        "i jego ustawienia.",
    "Disconnect account?": "Odłączyć konto?",
    "Disconnect {provider}? The backup stays on disk — you will need to sign in again "
    "to upload to the cloud.":
        "Odłączyć {provider}? Kopia zostanie tylko na dysku — trzeba będzie zalogować "
        "się ponownie, żeby wysyłać do chmury.",
    "This source is already on the list.": "To źródło już jest na liście.",
    "Paste the Client ID from Google Cloud (hint above).":
        "Wklej Client ID z Google Cloud (wskazówka wyżej).",
    "Choose a folder to back up": "Wybierz folder do backupu",
    "Choose files to back up": "Wybierz pliki do backupu",
    "Choose the destination folder": "Wybierz miejsce zapisu",
    "New backup": "Nowy backup",

    "Own client ID in 5 minutes": "Własny client ID w 5 minut",
    "Free, one-time, no card and no API keys.":
        "Darmowe, jednorazowe, bez karty i bez API keys.",
    "Sign in to your Google account and create a project (any name).":
        "Zaloguj się na swoje konto Google i utwórz projekt (dowolna nazwa).",
    "APIs & Services → Library → search “Google Drive API” → Enable.":
        "APIs & Services → Library → wyszukaj „Google Drive API” → Enable.",
    "OAuth consent screen: External, app name, your e-mail, then Publish app "
    "(Testing mode expires tokens after 7 days).":
        "OAuth consent screen: typ External, nazwa aplikacji, Twój e-mail, potem Publish "
        "app (w trybie Testing token wygasa po 7 dniach).",
    "Credentials → Create credentials → OAuth client ID → Desktop app.":
        "Credentials → Create credentials → OAuth client ID → typ Desktop app.",
    "Copy the Client ID and secret into the backup settings and click Connect.":
        "Skopiuj Client ID i Client secret do ustawień backupu i kliknij Połącz.",
    "Google will warn about an unverified app — it is your own app, so click "
    "Advanced → Go to …":
        "Google pokaże ostrzeżenie o niezweryfikowanej aplikacji — to Twoja własna "
        "aplikacja, więc kliknij Advanced → Go to …",
    "Open Google console": "Otwórz konsolę Google",
    "Close": "Zamknij",

    "Name your backup.": "Podaj nazwę backupu.",
    "A backup named “{name}” already exists.": "Backup o nazwie „{name}” już istnieje.",
    "Add a source or enable app data (Hermes / Obsidian).":
        "Dodaj źródło albo zaznacz dane aplikacji (Hermes / Obsidian).",
    "Source not found: {path}": "Nie znaleziono źródła: {path}",
    "Choose a destination.": "Wybierz miejsce zapisu.",
    "Destination must be a folder.": "Miejsce zapisu musi być folderem.",
    "Destination cannot be inside the source folder.":
        "Miejsce zapisu nie może znajdować się w folderze źródłowym.",
    "Hermes data not found on this computer.": "Nie znaleziono danych Hermesa na tym komputerze.",
    "Mnemosyne memory not found — choose the built-in one.":
        "Nie znaleziono pamięci Mnemosyne — wybierz wbudowaną.",
    "Built-in memory not found — choose Mnemosyne.":
        "Nie znaleziono wbudowanej pamięci — wybierz Mnemosyne.",
    "No Obsidian vaults found.": "Nie znaleziono sejfów Obsidiana.",
    "Destination cannot be inside the data you back up.":
        "Miejsce zapisu nie może leżeć w danych, które backupujesz.",
    "{provider} account is not connected — connect it in settings.":
        "Konto {provider} nie jest połączone — połącz je w ustawieniach.",
    "Rclone is not installed.": "Brak zainstalowanego rclone.",
    "Could not download rclone: {error}": "Nie udało się pobrać rclone: {error}",
    "Could not install rclone.": "Nie udało się zainstalować rclone.",
    "rclone did not start after unpacking.": "rclone nie uruchomił się po rozpakowaniu.",
    "The rclone package has no rclone.exe.": "Paczka rclone nie zawiera rclone.exe.",
    "The downloaded rclone archive is damaged.": "Pobrany plik rclone jest uszkodzony.",
    "Could not start rclone: {error}": "Nie udało się uruchomić rclone: {error}",
    "Sign-in was not finished (timeout).": "Logowanie nie zostało dokończone (upłynął czas).",
    "Sign-in rejected.": "Logowanie odrzucone.",
    "rclone did not return a token.": "rclone nie zwrócił tokenu logowania.",
    "Google Drive needs your own client ID (see README).":
        "Google Drive wymaga własnego client ID (patrz README).",
    "Unknown provider: {provider}": "Nieznany dostawca: {provider}",
    "Upload cancelled — the copy stays local only.":
        "Przerwano wysyłkę — kopia została tylko lokalnie.",
    "Upload took too long and was aborted.":
        "Wysyłka trwała zbyt długo i została przerwana.",
    "Account disconnected — connect it again.":
        "Konto zostało odłączone — połącz je ponownie.",
    "Wrong client ID / secret (see the Google guide).":
        "Błędny client ID / secret (sprawdź instrukcję Google).",
    "Cloud rejected the upload: {message}": "Chmura odrzuciła wysyłkę: {message}",
    "Cloud rejected the download: {message}": "Chmura odrzuciła pobieranie: {message}",
    "Cloud check failed: {message}": "Sprawdzenie chmury nie udało się: {message}",
    "The cloud did not answer in time.": "Chmura nie odpowiedziała w porę.",
    "Download cancelled.": "Przerwano pobieranie.",
    "The download took too long and was aborted.":
        "Pobieranie trwało zbyt długo i zostało przerwane.",
    "The download finished but the file is missing.":
        "Pobieranie się skończyło, ale pliku nie ma na dysku.",
    "⇣  Download": "⇣  Pobierz",
    "Checking the cloud…": "Sprawdzam chmurę…",
    "Checking the cloud for “{name}”…": "Sprawdzam chmurę: „{name}”…",
    "No copy in the cloud yet for “{name}” — run the backup with the cloud destination on.":
        "W chmurze nie ma jeszcze kopii „{name}” — uruchom backup z celem w chmurze.",
    "Save {filename} from the cloud ({size}) — pick a folder":
        "Zapisz {filename} z chmury ({size}) — wybierz folder",
    "Save {filename} from the cloud ({size}, {when}) — pick a folder":
        "Zapisz {filename} z chmury ({size}, {when}) — wybierz folder",
    "Downloading “{name}” from {provider}…": "Pobieram „{name}” z {provider}…",
    "Downloaded “{name}”: {size} → {path}": "Pobrano „{name}”: {size} → {path}",
    "Download failed: {message}": "Pobieranie nie udało się: {message}",
    "Downloading…": "Pobieranie…",
    "Stopping the download…": "Zatrzymuję pobieranie…",
    "Download stopped — no file was saved.":
        "Przerwano pobieranie — żaden plik nie został zapisany.",
    "Finish the current run first.": "Najpierw dokończ trwające kopiowanie.",
    "Finish the current download first.": "Najpierw dokończ trwające pobieranie.",
    "A download is in progress. Close the app?": "Trwa pobieranie. Zamknąć aplikację?",
    "Unknown rclone error": "nieznany błąd rclone",
    "Uploading {name} to {provider}…": "Wysyłam {name} do {provider}…",
    "Downloading rclone (~32 MB)…": "Pobieranie rclone (~32 MB)…",
    "Unpacking rclone…": "Rozpakowywanie rclone…",
    "Opening the browser — sign in and approve access…":
        "Otwieram przeglądarkę — zaloguj się i zatwierdź dostęp…",
    "Uploading files to {provider}…": "Wysyłam pliki do {provider}…",

    # Menu: kopia i przywracanie listy backupów
    "Menu": "Menu",
    "Backup list": "Backup listy",
    "Restore list": "Przywróć listę",
    "Local…": "Lokalnie…",
    "Cloud — no account connected": "Chmura — brak połączonego konta",
    "Save the list of backups": "Zapisz listę backupów",
    "Open a list of backups": "Otwórz listę backupów",
    "JSON file": "Plik JSON",
    "All files": "Wszystkie pliki",
    "The list is empty — add a backup first.":
        "Lista jest pusta — najpierw dodaj backup.",
    "Uploading the list to {provider}…": "Wysyłam listę do {provider}…",
    "Downloading the list from {provider}…": "Pobieram listę z {provider}…",
    "The list of {count} is in {provider} ({size})":
        "Lista ({count}) jest w {provider} ({size})",
    "Saved the list of {count}: {path}": "Zapisano listę: {count} → {path}",
    "Restoring the list…": "Przywracam listę…",
    "Restoring the list cancelled.": "Przywracanie listy anulowane.",
    "Restore the list?": "Przywrócić listę?",
    "Replace the current list ({current}) with {incoming} from {source}?\n\n"
    "The backup files themselves are not touched — only the list and its settings.":
        "Zastąpić obecną listę ({current}) listą {incoming} z {source}?\n\n"
        "Pliki kopii zostają nietknięte — zmieniają się tylko lista i jej ustawienia.",
    "Restored the list: {count}": "Przywrócono listę: {count}",
    "{missing} sources are missing on this computer":
        "brakuje {missing} źródeł na tym komputerze",
    "This file is not a BackupTool list.": "To nie jest lista BackupTool.",
    "This list is empty — there is nothing to restore.":
        "Ta lista jest pusta — nie ma czego przywracać.",
    "Could not read the list: {message}": "Nie udało się odczytać listy: {message}",
    "Could not save the list: {message}": "Nie udało się zapisać listy: {message}",
    "Could not restore the list: {message}":
        "Nie udało się przywrócić listy: {message}",
    "The list did not reach the cloud.": "Lista nie dotarła do chmury.",
    "No list in the cloud yet — save it first.":
        "W chmurze nie ma jeszcze listy — najpierw ją zapisz.",
    "Done": "Gotowe",
    "Done and uploaded": "Gotowe i wysłane",
    "Stopped": "Przerwano",
}

_current = [DEFAULT_LANGUAGE]

def set_language(language: str) -> None:
    if language in LANGUAGES:
        _current[0] = language

def language() -> str:
    return _current[0]

def t(text: str, **params) -> str:
    """Translate an English string to the active language and format it."""
    if _current[0] == "pl":
        text = PL.get(text, text)
    try:
        return text.format(**params) if params else text
    except (KeyError, IndexError, ValueError):
        return text
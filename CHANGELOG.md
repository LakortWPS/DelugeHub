# Changelog

All notable changes to this project are documented here.  
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.2.2] — 2026-06-30

### Fixed
- **AutoMatchWorker**: Thread-Absturz bei SD-Karten-Disconnect wird jetzt abgefangen — `error`-Signal + `QMessageBox` statt stillem Thread-Tod
- **Staging `_apply()`**: Exceptions werden jetzt via `logging` geloggt statt still geschluckt; `logging` auf Modul-Ebene statt inline-Import
- **Batch Import `.ogg`**: `_batch_import` nutzt jetzt `AUDIO_EXTENSIONS` aus `sd_scanner` — `.ogg`-Dateien wurden vorher ignoriert
- **Batch Export/Delete UI-Freeze**: `_batch_export_samples` und `_delete_unused_samples` laufen jetzt in einem `SimpleWorker`-Thread statt im Main-Thread
- **`_start_scan` Timeout**: `wait()` ohne Timeout ersetzt durch `wait(3000)` — verhindert potenzielle UI-Hänger beim Scan-Abbruch
- **Python 3.9 Kompatibilität**: `from __future__ import annotations` in `synth_utils.py` — `list[str] | None` Syntax funktioniert jetzt auch unter Python 3.9
- **App-Icon im Built**: Icon wird jetzt als eingebettete Bytes geladen statt per Dateipfad — funktioniert zuverlässig in Dev und PyInstaller-Build
- **Windows Taskleisten-Icon**: `SetCurrentProcessExplicitAppUserModelID` gesetzt — Icon erscheint korrekt in Taskleiste und Titelleiste

---

## [2.2.0] — 2026-06-08

### Fixed
- **Navigation nach Rescan**: App wirft nach jedem Rescan nicht mehr auf das Dashboard zurück — du bleibst auf der Seite auf der du warst. Nur der allererste Scan landet auf dem Dashboard
- **Worker Double-Start** (`batch_hub`, `backup_sync`): zweiter Klick auf Ausführen/Backup während ein Worker läuft wird jetzt geblockt mit Statusmeldung statt einem zweiten parallelen Worker
- **Silent Exceptions → Logging**: alle `except Exception: pass` Blöcke in `batch_hub`, `kit_manager`, `lost_sample_finder`, `sample_manager`, `song_manager`, `synth_editor` loggen jetzt via `logging.getLogger` (Warning/Debug je nach Schwere)

### Performance
- **XML-Dateilisten-Cache** (`file_ops.py`): `_all_xml_files()` baut die Liste einmalig pro Scan-Zyklus und cached sie; bei `rename_sample`/`move_sample` entfällt das wiederholte Iterieren über alle Dateien. Cache wird beim nächsten Scan-Start automatisch invalidiert

---

## [2.1.0] — 2026-06-08

### Added
- **Batch Hub — Rename-Schemas**: 5 wählbare Benennungsschemas für Songs, Kits und Synths:
  1. Deluge-Style (`A001, A002 … A009, B001 …`)
  2. Kompakt (`A1, A2 … A9, B1 …`)
  3. Freies Pattern (`{name}`, `{index}`, `{INDEX}`)
  4. Prefix + Nummer (`PREFIX001, PREFIX002 …`)
  5. Name + Affix (Prefix/Suffix um den Originalnamen)
- **Startindex-Spinner** (1–9999): Batch-Umbenennung beginnt bei beliebigem Index
- **Live-Vorschau-Spalte**: dritte Tabellenspalte zeigt neuen Namen sofort bei jeder Änderung (orange = geändert, grau = unverändert)

### Fixed
- **`_compute_rename` Letter-Overflow**: bei mehr als 234 Einträgen (> Z9) wurden ungültige ASCII-Zeichen (`[`, `\`, …) generiert; ersetzt durch Excel-ähnliche Doppelbuchstaben (`AA1, AB1 …`)

---

## [2.0.4] — 2026-05-20

### Fixed
- **Synth Editor — `_save_params` parameter collision**: tag-anchored replacement narrowed to parent element scope (e.g. search within `<osc1>…</osc1>`) — prevents `osc1/volume` and `osc2/volume` from overwriting each other when they share the same hex value
- **Installer** (`setup.iss`): deprecated `x64` architecture identifier replaced with `x64compatible`; removed obsolete `OnlyBelowVersion 6.1` QuickLaunch entry (Windows Vista-era, no longer applicable)

---

## [2.0.3] — 2026-05-09

### Fixed
- **StagingStore wiring** (`main_window.py`): shared `StagingStore` instance is now correctly injected into all modules via `set_staging()` loop and re-wired on SD path change; pending changes are restored from `.delugyhub_pending.json` on startup
- **Volume helpers centralized** (`core/volume_utils.py`): `vol_to_display`, `display_to_vol`, `vol_to_amp`, `amp_to_vol` moved to a shared module — removed three identical inline copies from `kit_manager`, `song_manager`, `batch_hub`
- **Kit Manager — normalize replace bug**: volume replacement now uses a `search_pos` tracker to prevent the wrong occurrence from being replaced when multiple pads share the same hex value
- **Sample Manager — audio playback**: switched primary audio loader to `soundfile`, which natively handles 24/32-bit WAV, AIF/AIFF, FLAC and OGG; stdlib `wave` kept as fallback for 16-bit WAV only
- **`models.py` — `files_with_missing`**: synths were not included in the missing-files list; all three content types (songs, kits, synths) are now returned
- **Synth Editor — `_save_params` replace collision**: parameter replacement is now anchored to the tag name (`>old_hex</tag>`) instead of a bare hex string, preventing a parameter with a coincidentally identical value from being overwritten
- **Lost Sample Finder — manual fix ignored**: `_manual_fix_row` wrote the chosen path to `ref.user_choice` (never read); corrected to `ref.resolution` so double-click manual assignments are actually applied on "Fixes anwenden"
- **Lost Sample Finder — `relative_to()` crash**: `ApplyFixWorker` now catches `ValueError` when the resolved path is outside the guessed SD root and falls back to the absolute path

---

## [2.0.2] — 2026-04-16

### Added
- **Windows Installer**: build system via PyInstaller + Inno Setup — produces a standalone `DelugeHub-x.x.x-Setup.exe` requiring no Python installation on the end user's machine; see `installer/README.md`

### Fixed
- **Batch Hub**: checkbox column header was truncated — replaced with `✓` icon and reduced column width to 30px
- **synth_editor.py**: null bytes appended during merge conflict removed — file is now valid Python again

---

## [2.0.1] — 2026-04-16

### Fixed
- **Import buttons** (Kit & Synth): now show a warning dialog when no SD folder is loaded instead of silently doing nothing
- **Button text clipping**: replaced `QMessageBox` with `QDialog` in PendingPanel — buttons now correctly adapt to their text width
- **Backup layout**: folder field moved inline into the page header, freeing up space for the actual content
- **Backup layout**: left panel split into a vertical `QSplitter` — create card and history table each get sufficient space; table scrolls correctly
- **Backup buttons**: `setFixedHeight` → `setMinimumHeight`; added `setMinimumWidth` for restore/delete buttons; increased `QMessageBox` button `min-width` to 120px
- **Toolbar labels** (Song, Kit, Synth): long button labels shortened with tooltips for full description — prevents text clipping on narrow windows
- **Tables**: removed `setMaximumWidth` from kit list, synth list and song detail panel — panels can now grow freely with the window
- **Delete buttons**: icon-only (`🗑`) with tooltip in all modules for a more compact toolbar

### Removed
- Theme toggle button from the main window header — theme is changed exclusively via Settings

---

## [2.0.0] — 2026-04-16

### Added
- **Staging System**: all destructive operations (XML edits, renames, deletes) are buffered in a `StagingStore` in RAM and only written to disk on explicit user command (overwrite originals or export to folder)
- **StagingStore** (`app/core/staging.py`): singleton-like in-memory buffer for `PendingChange` objects; auto-saves state as `.delugyhub_pending.json` on the SD card
- **PendingPanel** (`app/widgets/pending_panel.py`): QFrame widget per module — shows pending changes, save dialog (overwrite original / export to folder) and discard button
- **Status bar badge** in MainWindow: shows total pending changes across all modules + "Save all" button
- **Startup check**: when loading an SD folder, checks for `.delugyhub_pending.json` and restores pending changes if found
- **Backup: exclude samples option** — new checkbox "Without Samples folder (faster, smaller)"; stored in ZIP metadata

### Changed
- **Song Manager**, **Kit Manager**, **Synth Editor**, **Batch Hub**: all write operations now create `PendingChange` objects instead of writing directly (falls back to direct write if no StagingStore is set)
- **BatchWorker**: `finished` signal now also passes a list of `PendingChange` objects (QThread-safe: worker collects, main thread writes to store)
- **Version**: 1.1.0 → 2.0.0

---

## [1.1.0]

### Added
- Volume cap feature: song master, clip volumes, kit master, pad volumes
- Batch Hub: bulk operations across all songs/kits/synths
- Lost Sample Finder with auto-match and batch fix
- Backup & Sync module
- Settings module with theme selection (dark/light)

### Fixed
- XML parser for Deluge firmware 2.x format
- lxml recovery for corrupted XML files
- Various layout and column width bugs

---

## [1.0.4]
- Fix: broken Deluge XML files with missing closing tags (e.g. `</modKnobs>`) are now automatically repaired and loaded via lxml
- Fix: all table column headers fully visible — mode changed to `Interactive` with adjusted widths

## [1.0.3]
- Fix: XML parser now correctly handles Deluge firmware 2.0.0-beta format — files with `<firmwareVersion>` and `<earliestCompatibleFirmware>` before the main content element are parsed without errors
- Fix: unescaped `&` characters in Deluge XML files are automatically corrected to `&amp;`
- Fix: removed deprecated `Qt.AA_UseHighDpiPixmaps` warning on startup

## [1.0.2]
- Fix: app version in the sidebar is now loaded dynamically from `APP_VERSION`
- Fix: XML parser is robust against invalid control characters in Deluge files
- Fix: XML parser handles "junk after document element" — Deluge pads some files with null bytes after the root tag

## [1.0.1]
- Fix: `QLabel` backgrounds are now transparent — no visible box behind text on cards
- Fix: `QPushButton` no longer shows a dotted focus outline after clicking

## [1.0.0]
- Initial release

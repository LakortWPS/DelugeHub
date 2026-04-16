# DelugeHub v2.0.1

**All-in-One Synthstrom Deluge SD-Card Manager**

---

## Features

| Module | Description |
|---|---|
| 🎵 **Song Manager** | Browse, rename, duplicate and export songs with all dependencies |
| 🥁 **Kit Manager** | Edit kits & pad assignments, normalize and cap volumes |
| 🎹 **Synth Editor** | Edit parameters, randomizer, import/export |
| 📁 **Sample Manager** | Folder tree, preview, move/rename with automatic XML path update |
| 🔍 **Lost Sample Finder** | Find missing samples, auto-match, batch fix |
| ⚡ **Batch Hub** | Bulk rename, export, delete, normalize across all content types |
| 💾 **Backup & Sync** | Create ZIP backups, manage history, selectively restore |
| ⚙️ **Settings** | SD path, theme (dark/light), auto-scan |

---

## Installation

```bash
pip install -r requirements.txt
python main.py
```

**Optional audio preview** (Sample Manager):
```bash
pip install sounddevice numpy
```

---

## Project Structure

```
DelugeHub/
├── main.py                      ← Entry point
├── requirements.txt
├── CHANGELOG.md
├── installer/                   ← Windows installer build system
│   ├── DelugeHub.spec           ← PyInstaller config
│   ├── setup.iss                ← Inno Setup script
│   ├── build_installer.bat      ← One-click build script
│   └── README.md                ← Build instructions
├── app/
│   ├── main_window.py           ← Main window, StagingStore, status bar
│   ├── theme.py                 ← Dark + Light QSS stylesheets
│   ├── core/
│   │   ├── models.py            ← Data models (Song, Kit, Synth, …)
│   │   ├── xml_parser.py        ← Deluge XML parser (firmware 1.x + 2.x)
│   │   ├── sd_scanner.py        ← Async SD-card scanner
│   │   ├── file_ops.py          ← File operations + XML path update
│   │   ├── staging.py           ← StagingStore, PendingChange, ChangeType
│   │   ├── lost_finder.py       ← Lost sample logic
│   │   └── backup.py            ← Backup/restore, ZIP management
│   ├── widgets/
│   │   └── pending_panel.py     ← PendingPanel widget (staging display)
│   └── modules/
│       ├── song_manager.py
│       ├── kit_manager.py
│       ├── synth_editor.py
│       ├── sample_manager.py
│       ├── lost_sample_finder.py
│       ├── batch_hub.py
│       ├── backup_sync.py
│       └── settings_module.py
```

---

## Building a Windows Installer

See [installer/README.md](installer/README.md) for full instructions.

**Requirements:** PyInstaller + [Inno Setup 6](https://jrsoftware.org/isinfo.php)

```bat
installer\build_installer.bat
```

Output: `installer\output\DelugeHub-2.0.1-Setup.exe`

---

## Changelog

### v2.0.1 — 2026-04-16 · UI Fixes & Improvements

- **Fix:** Import buttons (Kit & Synth) now show an error message when no SD folder is loaded instead of silently doing nothing
- **Fix:** Button text was being clipped in dialogs — replaced `QMessageBox` with `QDialog` so buttons now scale to their text
- **Fix:** Backup page restructured: folder field moved inline into the header; create and history sections split into a vertical splitter — everything visible at once, history table scrollable
- **Fix:** Toolbar button labels shortened across all modules (full description via tooltip), no more text clipping on narrow windows
- **Fix:** Removed `setMaximumWidth` from tables and panels — content can now grow freely with the window
- **Removed:** Theme toggle button from the header — theme is now changed exclusively via Settings

### v2.0.0 — 2026-04-16 · Staging System

All write operations are now buffered and only committed to the SD card on explicit user command. No more accidental overwrites.

- **New: StagingStore** — in-memory buffer for all pending changes; persisted as `.delugyhub_pending.json` on the SD card and restored on next launch
- **New: PendingPanel** — each module shows pending changes; save to original path or export folder, discard with one click
- **New: Status bar badge** — shows total pending changes across all modules
- **New: Backup without Samples** — checkbox to skip the SAMPLES folder when creating a backup (faster, much smaller)
- **Changed:** Song Manager, Kit Manager, Synth Editor, Batch Hub — all write operations now use StagingStore (falls back to direct write if no store is set)

### v1.1.0 · Volume Cap & Stability

- **New:** Volume cap for song master, clip volumes, kit master, pad volumes
- **New:** Batch Hub — bulk operations across all songs/kits/synths
- **New:** Lost Sample Finder with auto-match
- **New:** Backup & Sync module
- **New:** Settings module with theme selection
- **Fix:** Various layout and stability issues

### v1.0.4
- Fix: Broken Deluge XML files with missing closing tags are now automatically repaired via lxml
- Fix: All table column headers fully visible

### v1.0.3
- Fix: XML parser now correctly handles Deluge firmware 2.0.0-beta format
- Fix: Unescaped `&` characters in XML files are automatically corrected

### v1.0.2
- Fix: App version is now loaded dynamically
- Fix: XML parser is robust against invalid control characters and null bytes

### v1.0.1
- Fix: QLabel backgrounds are transparent
- Fix: No focus outline after button click

### v1.0.0
- Initial release

---

## Community & License

- [Deluge Community](https://delugecommunity.com)
- MIT License

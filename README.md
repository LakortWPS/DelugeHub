# DelugeHub v2.0.1

**All-in-One Synthstrom Deluge SD Card Manager**

---

## Features

| Module | Description |
|---|---|
| 🎵 **Song Manager** | Manage, rename, duplicate, and export songs with all dependencies |
| 🥁 **Kit Manager** | Edit kits & pad assignments, normalize & limit volumes |
| 🎹 **Synth Editor** | Edit parameters, randomizer, import/export |
| 📁 **Sample Manager** | Folder tree, preview, move/rename with auto XML update |
| 🔍 **Lost Sample Finder** | Find missing samples, auto-match, batch fix |
| ⚡ **Batch Hub** | Batch operations: rename, export, delete, normalize for all content types |
| 💾 **Backup & Sync** | Create ZIP backups, manage history, selectively restore |
| ⚙️ **Settings** | SD path, Theme (Dark/Light), Auto-Scan |

---

## Installation

```bash
pip install -r requirements.txt
python main.py
```

**Optional Audio Preview** (Sample Manager):
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
├── app/
│   ├── main_window.py           ← Main window, StagingStore, Status Bar
│   ├── theme.py                 ← Dark + Light QSS
│   ├── core/
│   │   ├── models.py            ← Data models (Song, Kit, Synth, …)
│   │   ├── xml_parser.py        ← Deluge XML Parser (Firmware 1.x + 2.x)
│   │   ├── sd_scanner.py        ← Async SD Card Scanner
│   │   ├── file_ops.py          ← File operations + XML path update
│   │   ├── staging.py           ← StagingStore, PendingChange, ChangeType
│   │   ├── lost_finder.py       ← Lost sample logic
│   │   └── backup.py            ← Backup/Restore, ZIP management
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

## Changelog

### v2.0.1 — 2026-04-16 · UI fixes & improvements

- **Fix:** Import buttons (Kit & Synth) now display an error message if no SD folder is loaded — no more silent failure
- **Fix:** Button text in dialogs was truncated — `QMessageBox` replaced with `QDialog`, buttons now adjust to fit the text
- **Fix:** Backup page restructured: Backup folder field moved to the header for a compact layout; Create and History sections split into vertical splitters — everything visible at once, History table scrollable
- **Fix:* * Toolbar button labels shortened in all modules (full description via tooltip), no more text truncation in narrow windows
- **Fix:** `setMaximumWidth` removed from tables and panels — content can now expand freely with the window
- **Removed:** Theme toggle button from the header — The theme can now only be changed via Settings

---

### v2.0.0 — 2026-04-16 · Staging System

All write operations are now buffered and written to the SD card only upon explicit command. No more accidental overwrites.

- **New: StagingStore** — In-memory buffer for all pending changes; saved as `.delugyhub_pending.json` on the SD card and restored on the next startup
- **New: PendingPanel** — Each module displays pending changes; Save optionally to the original path or export folder; discard with a single click
- **New: Status Bar Badge** in the main window — displays the total number of pending changes across all modules
- **New: Backup without samples** — “Without samples folder” option when creating a backup (faster, significantly smaller)
- **Changed:** Song Manager, Kit Manager, Synth Editor, Batch Hub — all write operations now use StagingStore (falls back to direct writing if no store is set)

---

### v1.1.0 — Volume Cap & Stability

- **New:** Volume Cap for Song Master, Clip Volumes, Kit Master, Pad Volumes
- **New:** Batch Hub — bulk operations across all songs/kits/synths
- **New:** Lost Sample Finder with Auto-Match
- **New:** Backup & Sync module
- **New:** Settings module with theme selection
- **Fix:** Various layout and stability issues

---

### v1.0.4
- Fix: Corrupted Deluge XML files with missing closing tags are now fixed via lxml
- Fix: All table column headers are now fully visible

### v1.0.3
- Fix: XML parser correctly recognizes the Deluge Firmware 2.0.0-beta format
- Fix: Unescaped `&` characters in XML files are automatically corrected

### v1.0.2
- Fix: App version is loaded dynamically
- Fix: XML parser is robust against invalid control characters and null bytes

### v1.0.1
- Fix: QLabel backgrounds are transparent
- Fix: No focus border after button click

### v1.0.0
- Initial release

---

## Community & License

- [Deluge Community](https://delugecommunity.com)
- MIT License

# DelugeHub v2.0.2

**All-in-One Synthstrom Deluge SD Card Manager**

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

Output: `installer\output\DelugeHub-2.0.2-Setup.exe`

---

## Changelog

### v2.0.2 — 2026-04-16 · Installer & Fixes

- **New:** Windows installer build system (PyInstaller + Inno Setup) — produces a standalone `.exe`, no Python required on end user's machine; see `installer/README.md`
- **Fix:** Batch Hub checkbox column header was truncated — replaced with `✓` icon
- **Fix:** Null bytes in `synth_editor.py` from merge conflict removed

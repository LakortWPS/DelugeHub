# DelugeHub v1.0

**All-in-One Synthstrom Deluge SD-Card Manager**

## Features
- 🏠 **Dashboard** — SD-Card Health, Statistiken, Quick Actions
- 🎵 **Song Manager** — Songs verwalten, exportieren mit Dependencies
- 🥁 **Kit Manager** — Kits & Pad-Zuweisungen bearbeiten, Volumes normalisieren
- 🎹 **Synth Editor** — Parameter bearbeiten, Randomizer, Import/Export
- 📁 **Sample Manager** — Ordner-Tree, Vorschau, Move/Rename mit auto XML-Update
- 🔍 **Lost Sample Finder** — Fehlende Samples finden, Auto-Match, Batch-Fix
- ⚡ **Batch Hub** — Batch Rename/Export/Delete/Normalize für alle Inhaltstypen
- 💾 **Backup & Sync** — ZIP-Backups, Verlauf, selektives Wiederherstellen
- ⚙️ **Einstellungen** — SD-Pfad, Theme, Auto-Scan

## Installation

```bash
pip install -r requirements.txt
python main.py
```

### Optionale Audio-Vorschau (Sample Manager):
```bash
pip install sounddevice numpy
```

## Starten
```bash
python main.py
```

## Projektstruktur
```
delugyhub/
├── main.py                      ← Entry point
├── requirements.txt
├── app/
│   ├── main_window.py           ← Hauptfenster
│   ├── theme.py                 ← Dark + Light QSS
│   ├── core/
│   │   ├── models.py            ← Datenmodelle
│   │   ├── xml_parser.py        ← Deluge XML Parser
│   │   ├── sd_scanner.py        ← Async Scanner
│   │   ├── file_ops.py          ← Datei-Operationen + XML-Update
│   │   ├── lost_finder.py       ← Lost Sample Logik
│   │   └── backup.py            ← Backup/Restore
│   └── modules/
│       ├── dashboard.py
│       ├── song_manager.py
│       ├── kit_manager.py
│       ├── synth_editor.py
│       ├── sample_manager.py
│       ├── lost_sample_finder.py
│       ├── batch_hub.py
│       ├── backup_sync.py
│       └── settings_module.py
```

## Community
- https://delugecommunity.com
- MIT License

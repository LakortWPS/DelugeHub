# DelugeHub v1.0.2

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

## Changelog

### v1.0.2
- Fix: App-Version in der Sidebar wird jetzt dynamisch aus `APP_VERSION` geladen (war hardcoded `v1.0`)
- Fix: XML-Parser ist jetzt robust gegen ungültige Steuerzeichen in Deluge-Dateien (`invalid token`)
- Fix: XML-Parser behandelt jetzt "junk after document element" — Deluge paddet manche Dateien mit Null-Bytes nach dem Root-Tag

### v1.0.1
- Fix: `QLabel`-Hintergründe sind jetzt transparent — kein sichtbarer Kasten mehr hinter Texten auf Karten
- Fix: `QPushButton` zeigt nach dem Klicken keinen gepunkteten Fokus-Rahmen mehr

### v1.0.0
- Erster Release

## Community
- https://delugecommunity.com
- MIT License

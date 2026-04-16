# DelugeHub v2.0.1

**All-in-One Synthstrom Deluge SD-Card Manager**

---

## Features

| Modul | Beschreibung |
|---|---|
| 🎵 **Song Manager** | Songs verwalten, umbenennen, duplizieren, exportieren mit allen Dependencies |
| 🥁 **Kit Manager** | Kits & Pad-Zuweisungen bearbeiten, Volumes normalisieren & begrenzen |
| 🎹 **Synth Editor** | Parameter bearbeiten, Randomizer, Import/Export |
| 📁 **Sample Manager** | Ordner-Tree, Vorschau, Move/Rename mit auto XML-Update |
| 🔍 **Lost Sample Finder** | Fehlende Samples finden, Auto-Match, Batch-Fix |
| ⚡ **Batch Hub** | Massenoperationen: Rename, Export, Delete, Normalize für alle Inhaltstypen |
| 💾 **Backup & Sync** | ZIP-Backups erstellen, Verlauf verwalten, selektiv wiederherstellen |
| ⚙️ **Einstellungen** | SD-Pfad, Theme (Dark/Light), Auto-Scan |

---

## Installation

```bash
pip install -r requirements.txt
python main.py
```

**Optionale Audio-Vorschau** (Sample Manager):
```bash
pip install sounddevice numpy
```

---

## Projektstruktur

```
DelugeHub/
├── main.py                      ← Entry point
├── requirements.txt
├── CHANGELOG.md
├── app/
│   ├── main_window.py           ← Hauptfenster, StagingStore, Status-Bar
│   ├── theme.py                 ← Dark + Light QSS
│   ├── core/
│   │   ├── models.py            ← Datenmodelle (Song, Kit, Synth, …)
│   │   ├── xml_parser.py        ← Deluge XML Parser (Firmware 1.x + 2.x)
│   │   ├── sd_scanner.py        ← Async SD-Card Scanner
│   │   ├── file_ops.py          ← Datei-Operationen + XML-Pfad-Update
│   │   ├── staging.py           ← StagingStore, PendingChange, ChangeType
│   │   ├── lost_finder.py       ← Lost Sample Logik
│   │   └── backup.py            ← Backup/Restore, ZIP-Verwaltung
│   ├── widgets/
│   │   └── pending_panel.py     ← PendingPanel Widget (Staging-Anzeige)
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

### v2.0.1 — 2026-04-16 · UI-Fixes & Verbesserungen

- **Fix:** Import-Buttons (Kit & Synth) zeigen jetzt eine Fehlermeldung wenn kein SD-Ordner geladen ist — kein stilles Nichts mehr
- **Fix:** Button-Texte in Dialogen wurden abgeschnitten — `QMessageBox` durch `QDialog` ersetzt, Buttons passen sich jetzt an den Text an
- **Fix:** Backup-Seite neu strukturiert: Backup-Ordner-Feld kompakt in den Header verschoben; Create- und History-Bereich in vertikalen Splitter aufgeteilt — alles auf einmal sichtbar, History-Tabelle scrollbar
- **Fix:** Toolbar-Button-Labels in allen Modulen gekürzt (vollständige Beschreibung per Tooltip), kein Text-Abschneiden mehr bei schmalem Fenster
- **Fix:** `setMaximumWidth` auf Tabellen und Panels entfernt — Inhalte können jetzt frei mit dem Fenster wachsen
- **Entfernt:** Theme-Toggle-Button aus dem Header — Theme wird ausschließlich über Einstellungen geändert

---

### v2.0.0 — 2026-04-16 · Staging System

Alle schreibenden Operationen werden jetzt gepuffert und erst auf expliziten Befehl auf die SD-Card geschrieben. Kein versehentliches Überschreiben mehr.

- **Neu: StagingStore** — In-Memory-Buffer für alle ausstehenden Änderungen; wird als `.delugyhub_pending.json` auf der SD-Card gespeichert und beim nächsten Start wiederhergestellt
- **Neu: PendingPanel** — Jedes Modul zeigt ausstehende Änderungen an; Speichern wahlweise in Originalpfad oder Export-Ordner, Verwerfen mit einem Klick
- **Neu: Status-Bar-Badge** im Hauptfenster — zeigt Gesamtanzahl ausstehender Änderungen über alle Module
- **Neu: Backup ohne Samples** — Option "Ohne Samples-Ordner" beim Backup erstellen (schneller, deutlich kleiner)
- **Geändert:** Song Manager, Kit Manager, Synth Editor, Batch Hub — alle schreibenden Operationen nutzen jetzt StagingStore (Fallback auf Direktschreiben wenn kein Store gesetzt)

---

### v1.1.0 — Volume Cap & Stabilität

- **Neu:** Volume Cap für Song-Master, Clip-Volumes, Kit-Master, Pad-Volumes
- **Neu:** Batch Hub — Massenoperationen über alle Songs/Kits/Synths
- **Neu:** Lost Sample Finder mit Auto-Match
- **Neu:** Backup & Sync Modul
- **Neu:** Settings-Modul mit Theme-Wahl
- **Fix:** Diverse Layout- und Stabilitätsprobleme

---

### v1.0.4
- Fix: Kaputte Deluge XML-Dateien mit fehlenden Closing-Tags werden via lxml automatisch repariert
- Fix: Alle Tabellen-Spaltenheader vollständig sichtbar

### v1.0.3
- Fix: XML-Parser erkennt Deluge Firmware 2.0.0-beta Format korrekt
- Fix: Unescapte `&`-Zeichen in XML-Dateien werden automatisch korrigiert

### v1.0.2
- Fix: App-Version wird dynamisch geladen
- Fix: XML-Parser robust gegen ungültige Steuerzeichen und Null-Bytes

### v1.0.1
- Fix: QLabel-Hintergründe transparent
- Fix: Kein Fokus-Rahmen nach Button-Klick

### v1.0.0
- Erster Release

---

## Community & Lizenz

- [Deluge Community](https://delugecommunity.com)
- MIT License

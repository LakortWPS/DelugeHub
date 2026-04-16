# Changelog

Alle nennenswerten Änderungen am Projekt werden hier dokumentiert.  
Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [2.0.1] — 2026-04-16

### Fixed
- **Import-Buttons** (Kit & Synth): Zeigen jetzt eine Fehlermeldung wenn kein SD-Ordner geladen ist, statt stumm nichts zu tun
- **Button-Text abgeschnitten**: QMessageBox durch QDialog ersetzt in PendingPanel → Buttons passen sich jetzt korrekt an den Text an
- **Backup-Layout**: Konfigurationsfeld (Backup-Ordner) in den Header verschoben — spart Platz für den eigentlichen Inhalt
- **Backup-Layout**: Linke Seite in vertikalen QSplitter aufgeteilt → Create-Bereich und History-Tabelle erhalten beide ausreichend Platz, Tabelle scrollt korrekt
- **Backup-Buttons**: `setFixedHeight` → `setMinimumHeight`, `setMinimumWidth` für Wiederherstellen/Löschen-Buttons, QMessageBox-Button `min-width` auf 120px erhöht
- **Toolbar-Labels** (Song, Kit, Synth): Zu lange Button-Beschriftungen gekürzt ("Volumes normalisieren" → "Normalisieren", "Master-Vol." → "Master", etc.) mit Tooltips für Details
- **Tabellen**: `setMaximumWidth` auf Kit-Liste, Synth-Liste und Song-Detail-Panel entfernt → Panels können frei mit dem Fenster wachsen
- **Löschen-Buttons**: Icon-only (`🗑`) mit Tooltip in allen Modulen für kompaktere Toolbar

### Removed
- **Theme-Toggle-Button** im Header entfernt — Theme wird ausschließlich über Einstellungen geändert

---

## [2.0.0] — 2026-04-16

### Added
- **Staging System**: Alle destruktiven Operationen (XML-Bearbeitung, Umbenennen, Löschen) werden in einem `StagingStore` im RAM gepuffert und erst auf expliziten Befehl auf die SD-Card geschrieben
- **StagingStore** (`app/core/staging.py`): Singleton-ähnlicher In-Memory-Buffer mit `PendingChange`-Objekten; speichert Pending-State als `.delugyhub_pending.json` auf der SD-Card
- **PendingPanel** (`app/widgets/pending_panel.py`): QFrame-Widget pro Modul — zeigt ausstehende Änderungen, Save-Dialog (Original überschreiben / In anderen Ordner exportieren) und Verwerfen-Button
- **Status-Bar-Badge** in MainWindow: zeigt Gesamtanzahl ausstehender Änderungen + "Alle speichern"-Button
- **Startup-Check**: Beim Laden eines SD-Ordners wird geprüft ob eine `.delugyhub_pending.json` vorhanden ist und ggf. wiederhergestellt
- **Backup: Ohne Samples-Option** — neue Checkbox "Ohne Samples-Ordner (schneller, kleiner)" im Backup-Bereich; wird in ZIP-Metadaten gespeichert

### Changed
- **Song Manager**, **Kit Manager**, **Synth Editor**, **Batch Hub**: Alle schreibenden Operationen erstellen jetzt `PendingChange`-Objekte statt direkt zu schreiben (Fallback auf Direktschreiben wenn kein StagingStore gesetzt)
- **BatchWorker**: `finished`-Signal übergibt jetzt zusätzlich eine Liste von `PendingChange`-Objekten (QThread-safe: Worker sammelt, Main-Thread schreibt in Store)
- **Version**: 1.1.0 → 2.0.0

---

## [1.1.0] — 2025 (stabil)

### Added
- **Volume Cap Feature**: Song-Master, Clip-Volumes, Kit-Master, Pad-Volumes auf Maximalwert begrenzen
- **Batch Hub**: Massenoperationen über alle Songs/Kits/Synths gleichzeitig
- **Lost Sample Finder**: Fehlende Sample-Referenzen erkennen und reparieren
- **Backup & Sync**: SD-Card-Backups als ZIP erstellen, Verlauf verwalten, selektiv wiederherstellen
- **Settings-Modul**: Theme-Wahl (Dark/Light), App-Infos

### Fixed
- XML-Parser für Firmware 2.x Deluge-Format
- lxml-Recovery bei beschädigten XML-Dateien
- Diverse Layout- und Spalten-Bugs in Tabellen

---

## [1.0.0] — 2025

### Added
- Initiales Release: DelugeHub v1.0.0
- **Song Manager**: Songs durchsuchen, umbenennen, duplizieren, exportieren
- **Kit Manager**: Kits durchsuchen, Pad-Grid anzeigen, Volumes normalisieren
- **Synth Editor**: Synths durchsuchen, Parameter bearbeiten, Randomizer
- SD-Card-Ordner auswählen und scannen
- Dark/Light Theme

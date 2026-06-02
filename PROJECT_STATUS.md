# DelugeHub — Projektstand

**Stand:** 2026-06-02  
**Version:** 2.0.4 (Branch: `main`)

---

## Was ist DelugeHub?

**All-in-One SD-Card Manager für den Synthstrom Deluge** (Desktop-App, Python + PySide6).  
Verwaltet Songs, Kits, Synths, Samples und Backups direkt auf der SD-Karte des Geräts.

---

## Projektstruktur

```
DelugeHub/
├── main.py                        ← Entry Point (QApplication + MainWindow)
├── requirements.txt               ← PySide6>=6.6.0, lxml>=5.0.0 (+ opt. sounddevice/numpy)
├── app/
│   ├── main_window.py             ← Hauptfenster + Sidebar Navigation
│   ├── theme.py                   ← Dark + Light QSS Themes
│   ├── widgets/
│   │   ├── toast.py               ← Toast-Benachrichtigung Widget
│   │   └── pending_panel.py       ← PendingPanel Widget (Staging-Anzeige pro Modul)
│   ├── core/
│   │   ├── models.py              ← Datenmodelle (Song, Kit, Synth, Sample, …)
│   │   ├── xml_parser.py          ← Deluge XML Parser (lxml-basiert, auto-repair)
│   │   ├── sd_scanner.py          ← Async SD-Karten Scanner
│   │   ├── file_ops.py            ← Datei-Operationen + XML auto-update
│   │   ├── lost_finder.py         ← Lost Sample Logik
│   │   ├── backup.py              ← ZIP-Backup / Restore (+ exclude_samples Option)
│   │   └── staging.py             ← StagingStore + PendingChange (v2.0.0)
│   └── modules/
│       ├── dashboard.py           ← SD-Health, Statistiken, Quick Actions
│       ├── song_manager.py        ← Songs verwalten + Export mit Dependencies
│       ├── kit_manager.py         ← Kits & Pad-Zuweisungen, Volume normalisieren
│       ├── synth_editor.py        ← Synth-Parameter, Randomizer, Import/Export
│       ├── sample_manager.py      ← Ordner-Tree, Vorschau, Move/Rename + XML-Update
│       ├── lost_sample_finder.py  ← Fehlende Samples finden, Auto-Match, Batch-Fix
│       ├── batch_hub.py           ← Batch Rename/Export/Delete/Normalize
│       ├── backup_sync.py         ← Backup-UI, Verlauf, selektives Restore
│       ├── settings_module.py     ← SD-Pfad, Theme, Auto-Scan (APP_VERSION hier)
│       └── placeholder.py         ← Platzhalter-Modul
```

---

## Git-Historie (letzte Commits)

| Hash | Branch | Beschreibung |
|------|--------|-------------|
| `f710872` | `main` | v2.0.4 — bugfix release |
| `541007e` | `main` | fix: synth_editor parent-block replacement, inno warnings, gitignore |
| `18a9e89` | `main` | v2.0.3 — bugfix release |
| `c86d116` | `main` | merge: integrate remote changes |
| `e3530d4` | `main` | chore: update gitignore to exclude Deluge SD card files |

---

## Aktueller Status

### ✅ v2.0.4 aktueller Stand (2026-06-02)

| Feature | Status |
|---|---|
| Staging-System (`StagingStore` + `PendingPanel`) | ✅ seit v2.0.0 |
| Undo/Redo History (`ActionHistory`) | ✅ aktiv — `main_window.py` initialisiert und verteilt an alle Module |
| Volume-Utils zentralisiert (`core/volume_utils.py`) | ✅ seit v2.0.3 |
| Synth Editor — parent-block-anchored replacement | ✅ seit v2.0.4 |
| Line-Ending-Normalisierung | ✅ bereinigt (v2.0.4) |

### Staging-Architektur

- `StagingStore` hält alle ausstehenden Änderungen im RAM, autosaved als `.delugyhub_pending.json` auf der SD-Card
- Jedes Modul hat ein `PendingPanel` am unteren Rand (nur sichtbar wenn Änderungen vorhanden)
- MainWindow-Statusleiste zeigt Gesamtanzahl + "Alle speichern"-Button
- Beim Speichern: Original überschreiben ODER in anderen Ordner exportieren
- Beim App-Start mit SD-Card: Restore-Dialog wenn Session-Pending vorhanden

### Undo/Redo-System

- `app/core/history.py` — `ActionHistory` (30-Step Undo/Redo Stack)
- Wird in `main_window.py:88` initialisiert und via `set_history()` an alle Module übergeben
- Module mit Undo-Support: `kit_manager`, `synth_editor`, `sample_manager`, `lost_sample_finder`
- `if self._history:` Guards sind **intentional** — defensiv für den Zeitraum vor `set_history()`

---

## Offene Punkte / Nächste Schritte

Keine bekannten offenen Punkte.

---

## Wichtige Konventionen (für Agenten)

- **XML lesen:** immer `_parse_xml_robust(path)` aus `core/xml_parser.py` — niemals `ET.parse()`
- **Dateien lesen/schreiben:** immer `_read_xml(path)` / `_write_xml(path, content, enc)` aus `core/file_ops.py`
- **Glob auf Linux:** immer beide Patterns `*.XML` + `*.xml` sammeln
- `core/history.py` — `ActionHistory`-Klasse, initialisiert in `main_window.py`, via `set_history()` an Module verteilt

## Skills & Workflows

- **Neue Features:** `brainstorming` → `writing-plans` → `using-git-worktrees` → `executing-plans`
- **Bugs:** `systematic-debugging` → Fix → `verification-before-completion`
- **Code Review:** `requesting-code-review` / `engineering:code-review`
- **Fertig stellen:** `finishing-a-development-branch`

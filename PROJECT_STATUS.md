# DelugeHub — Projektstand

**Stand:** 2026-09-16  
**Version:** 2.2.3 (Branch: `main`)

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
| `e31a991` | `main` | Merge PR #3: Doku-Korrektur, CI, 5 Datensicherheits-Fixes, Startup-Crash-Fix |
| `0c5c329` | `main` | fix: App-Crash beim Start wenn sounddevice/soundfile native Libs fehlen |
| `9f1e340` | `main` | fix: gescopter Pad-Sample-Replace, Lost-Finder-Autotick, XML-Validity-Guard |
| `49bab4b` | `main` | fix: Batch-Rename-Kollision, Kit/Song-Trash, sicherer Volume-Replace |
| `18856b2` | `main` | test: tote Test-Stubs entfernt, CI-Workflow hinzugefügt |
| `901ff6a` | `main` | docs: veraltete PROJECT_STATUS.md-Punkte korrigiert |
| `7d450c8` | `main` | release: v2.2.2 — Bugfixes + Python 3.9 + Icon-Fix |
| `fea7501` | `main` | chore: Version bump 2.2.2 |
| `9474d36` | `main` | fix: Icon als eingebettete Bytes laden (kein Dateipfad, PyInstaller-sicher) |
| `14835e6` | `main` | fix: Windows AppUserModelID für korrektes Icon in Taskleiste + Fenster |
| `0699cb9` | `main` | fix: Python 3.9 Kompatibilität in synth_utils (list[str] \| None) |
| `b676d79` | `main` | fix: Bug #1-4 + Issue #1 aus Code-Audit |
| `b244efd` | `main` | v2.2.1: Keyboard-Shortcuts, globale Suche, Replace-Vorschau + Bugfixes |
| `2fa0549` | `main` | fix: icon in taskbar bei PyInstaller-Build (sys._MEIPASS + datas) |
| `95dc555` | `main` | fix: restore missing batch_hub methods lost during rebase |
| `5f537c1` | `main` | Remove outdated sections from README |

---

## Aktueller Status

### ✅ v2.0.0 Staging-System implementiert (2026-04-16)

Alle destruktiven Operationen (XML-Edit, Rename, Delete) werden jetzt gepuffert und erst auf expliziten Nutzerbefehl auf Disk geschrieben.

| Komponente | Status |
|---|---|
| `app/core/staging.py` — StagingStore + PendingChange | ✅ NEU |
| `app/widgets/pending_panel.py` — PendingPanel Widget | ✅ NEU |
| `app/main_window.py` — Staging-Badge + Alle-Speichern | ✅ geändert |
| `app/modules/song_manager.py` | ✅ geändert |
| `app/modules/kit_manager.py` | ✅ geändert |
| `app/modules/synth_editor.py` | ✅ geändert |
| `app/modules/batch_hub.py` — QThread-safe via Signal | ✅ geändert |
| `app/core/backup.py` + `backup_sync.py` — exclude_samples | ✅ geändert |

### Staging-Architektur

- `StagingStore` hält alle ausstehenden Änderungen im RAM, autosaved als `.delugyhub_pending.json` auf der SD-Card
- Jedes Modul hat ein `PendingPanel` am unteren Rand (nur sichtbar wenn Änderungen vorhanden)
- MainWindow-Statusleiste zeigt Gesamtanzahl + "Alle speichern"-Button
- Beim Speichern: Original überschreiben ODER in anderen Ordner exportieren
- Beim App-Start mit SD-Card: Restore-Dialog wenn Session-Pending vorhanden

### Line-Endings — erledigt
`.gitattributes` erzwingt `* text=auto` + explizite `eol=lf`-Regeln für `.py`/`.md`/`.txt`/`.yml`/`.yaml`/`.json`. Verifiziert per `git grep` auf `\r` in `*.py`: 0 Treffer. Kein offener Punkt mehr.

### History-System — erledigt
`app/core/history.py` existiert (`ActionHistory`, `Action`, `move_to_trash`/`restore_from_trash`). `main_window.py` (Zeile ~434) verdrahtet es aktiv: `for module in self._modules.values(): if hasattr(module, "set_history"): module.set_history(self._history)`. Die `if self._history:`-Guards in `kit_manager.py`, `lost_sample_finder.py`, `sample_manager.py`, `synth_editor.py` sind kein toter Code — `self._history` ist zur Laufzeit ein initialisiertes `ActionHistory`-Objekt.

### Volume-Helper — kein Duplikat
`kit_manager.py` und `batch_hub.py` importieren beide `vol_to_display`/`display_to_vol` aus der gemeinsamen `core/volume_utils.py` (kein lokal duplizierter Code).

---

## Offene Punkte / Nächste Schritte

Aktuell keine bekannten offenen Punkte aus früheren Audits — die drei oben genannten wurden mit Stand 2026-09-16 verifiziert und sind erledigt. Neue offene Punkte hier eintragen, sobald sie identifiziert sind.

---

## Wichtige Konventionen (für Agenten)

- **XML lesen:** immer `_parse_xml_robust(path)` aus `core/xml_parser.py` — niemals `ET.parse()`
- **Dateien lesen/schreiben:** immer `_read_xml(path)` / `_write_xml(path, content, enc)` aus `core/file_ops.py`
- **Glob auf Linux:** immer beide Patterns `*.XML` + `*.xml` sammeln
- `core/history.py` existiert und ist über `main_window.py` an alle Module mit `set_history` verdrahtet — nicht erneut anlegen

## Skills & Workflows

- **Neue Features:** `brainstorming` → `writing-plans` → `using-git-worktrees` → `executing-plans`
- **Bugs:** `systematic-debugging` → Fix → `verification-before-completion`
- **Code Review:** `requesting-code-review` / `engineering:code-review`
- **Fertig stellen:** `finishing-a-development-branch`

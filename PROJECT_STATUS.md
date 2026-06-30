# DelugeHub — Projektstand

**Stand:** 2026-06-30  
**Version:** 2.2.2 (Branch: `main`)

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
| `a78ead6` | `main` | chore: bump version to 2.0.0 (staging system major release) |
| `19855ff` | `main` | feat: backup supports exclude_samples option |
| `129ee85` | `main` | feat: batch_hub uses StagingStore |
| `1d1dee9` | `main` | feat: synth_editor uses StagingStore |
| `f01b1ac` | `main` | feat: kit_manager uses StagingStore |
| `c0da3ca` | `main` | feat: song_manager uses StagingStore |
| `4c7fa9d` | `main` | feat: add StagingStore to MainWindow + status bar badge |
| `8729152` | `main` | feat: add PendingPanel widget |
| `f27a17e` | `main` | feat: add StagingStore core module |

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

### Line-Ending-Drift (noch offen)
Mehrere Dateien auf `main` zeigen `M`-Status (CRLF↔LF), kein inhaltlicher Code-Unterschied. Noch nicht bereinigt.

---

## Offene Punkte / Nächste Schritte

1. **Line-Endings bereinigen** — `.gitattributes` mit `* text=auto` + `git add --renormalize .`
2. **Minor/Code-Quality (aufgeschoben):**
   - History-System nie initialisiert — toter Code in allen Modulen (`_history` immer `None`)
   - Volume-Helper (`_vol_to_display` / `_display_to_vol`) dupliziert in `kit_manager` + `batch_hub`

---

## Wichtige Konventionen (für Agenten)

- **XML lesen:** immer `_parse_xml_robust(path)` aus `core/xml_parser.py` — niemals `ET.parse()`
- **Dateien lesen/schreiben:** immer `_read_xml(path)` / `_write_xml(path, content, enc)` aus `core/file_ops.py`
- **Glob auf Linux:** immer beide Patterns `*.XML` + `*.xml` sammeln
- `core/history.py` existiert nicht — alle `if self._history:` Guards sind toter Code

## Skills & Workflows

- **Neue Features:** `brainstorming` → `writing-plans` → `using-git-worktrees` → `executing-plans`
- **Bugs:** `systematic-debugging` → Fix → `verification-before-completion`
- **Code Review:** `requesting-code-review` / `engineering:code-review`
- **Fertig stellen:** `finishing-a-development-branch`

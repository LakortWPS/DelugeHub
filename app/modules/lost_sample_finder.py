"""
DelugeHub — Lost Sample Finder Module
Find, auto-match and repair missing sample references across all XML files.
"""
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QFrame, QProgressBar, QMessageBox, QAbstractItemView,
    QSplitter, QScrollArea, QCheckBox, QLineEdit, QComboBox
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QColor, QFont

from ..core.models import SDCardIndex
from ..core.lost_finder import (
    MissingRef, collect_missing_refs, auto_match_all, search_folder_for_missing
)
from ..core.file_ops import fix_xml_path, update_xml_path

log = logging.getLogger(__name__)


# ── Background worker for auto-match ──────────────────────────────────────
class AutoMatchWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, refs: list, sd_root: Path):
        super().__init__()
        self.refs = refs
        self.sd_root = sd_root

    def run(self):
        try:
            self.progress.emit(5, "Erstelle Datei-Index…")
            auto_match_all(self.refs, self.sd_root)
            self.progress.emit(100, "Auto-Match abgeschlossen.")
            self.finished.emit(self.refs)
        except Exception as e:
            log.error("AutoMatchWorker fehlgeschlagen: %s", e)
            self.error.emit(str(e))


# ── Apply fixes worker ─────────────────────────────────────────────────────
class ApplyFixWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)  # {"fixed": int, "failed": int}

    def __init__(self, refs: list[MissingRef]):
        super().__init__()
        self.refs = refs

    def run(self):
        fixed = failed = 0
        ready = [r for r in self.refs if r.resolution and not r.fixed]
        total = len(ready)

        for i, ref in enumerate(ready):
            try:
                new_rel = str(ref.resolution.relative_to(
                    _guess_sd_root(ref.xml_file)
                )).replace("\\", "/")
            except ValueError:
                # resolution is not inside the guessed SD root — use absolute path
                new_rel = str(ref.resolution).replace("\\", "/")

            ok = update_xml_path(ref.xml_file, ref.broken_path, new_rel)
            if ok:
                ref.fixed = True
                fixed += 1
            else:
                failed += 1

            pct = int((i + 1) / max(total, 1) * 100)
            self.progress.emit(pct, f"Fixing: {ref.filename}")

        self.finished.emit({"fixed": fixed, "failed": failed})


def _guess_sd_root(xml_file: Path) -> Path:
    """Walk up from xml_file to find the SD root (parent of SONGS/KITS/SYNTHS)."""
    p = xml_file.parent
    while p.parent != p:
        if p.name.upper() in ("SONGS", "KITS", "SYNTHS"):
            return p.parent
        p = p.parent
    return p


# ── Column indices ─────────────────────────────────────────────────────────
COL_SEL   = 0
COL_TYPE  = 1
COL_XML   = 2
COL_MISSING = 3
COL_MATCH = 4
COL_CONF  = 5
COL_STATUS = 6


class LostSampleFinderModule(QWidget):
    request_rescan = Signal()

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._refs: list[MissingRef] = []
        self._worker = None
        self._history = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(self._lbl("🔍  Lost Sample Finder", "PageTitle"))
        title_col.addWidget(self._lbl("Fehlende Sample-Referenzen finden und reparieren", "PageSubtitle"))
        hdr.addLayout(title_col)
        hdr.addStretch()

        self._scan_btn = QPushButton("🔎  Analysieren")
        self._scan_btn.setFixedHeight(38)
        self._scan_btn.clicked.connect(self._run_analysis)
        hdr.addWidget(self._scan_btn)
        root.addLayout(hdr)
        root.addSpacing(16)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("Card")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)

        self._auto_match_btn = QPushButton("⚡  Auto-Match")
        self._auto_match_btn.setToolTip("Versucht automatisch alle fehlenden Samples anhand des Dateinamens zu finden")
        self._auto_match_btn.clicked.connect(self._run_auto_match)
        self._auto_match_btn.setEnabled(False)

        self._search_folder_btn = QPushButton("📂  Ordner durchsuchen")
        self._search_folder_btn.setObjectName("SecondaryButton")
        self._search_folder_btn.setToolTip("Externen Ordner nach fehlenden Samples durchsuchen")
        self._search_folder_btn.clicked.connect(self._search_in_folder)
        self._search_folder_btn.setEnabled(False)

        self._apply_btn = QPushButton("✅  Fixes anwenden")
        self._apply_btn.setObjectName("SuccessButton")
        self._apply_btn.setToolTip("Alle gematchten Pfade in den XML-Dateien reparieren")
        self._apply_btn.clicked.connect(self._apply_fixes)
        self._apply_btn.setEnabled(False)

        self._export_btn = QPushButton("📄  Report exportieren")
        self._export_btn.setObjectName("SecondaryButton")
        self._export_btn.clicked.connect(self._export_report)
        self._export_btn.setEnabled(False)

        self._sel_all_cb = QCheckBox("Alle auswählen")
        self._sel_all_cb.stateChanged.connect(self._toggle_select_all)

        tb_layout.addWidget(self._sel_all_cb)
        tb_layout.addWidget(self._auto_match_btn)
        tb_layout.addWidget(self._search_folder_btn)
        tb_layout.addWidget(self._apply_btn)
        tb_layout.addStretch()
        tb_layout.addWidget(self._export_btn)
        root.addWidget(toolbar)
        root.addSpacing(8)

        # Filter bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(8)
        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filtern nach Dateiname, Pfad…")
        self._filter_edit.textChanged.connect(self._apply_filter)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["Alle", "Nur Song", "Nur Kit", "Nur Synth",
                                      "Nur gematchte", "Nur nicht gematchte"])
        self._filter_combo.setFixedWidth(180)
        self._filter_combo.currentIndexChanged.connect(self._apply_filter)

        filter_bar.addWidget(QLabel("Filter:"))
        filter_bar.addWidget(self._filter_edit, 1)
        filter_bar.addWidget(self._filter_combo)
        root.addLayout(filter_bar)
        root.addSpacing(8)

        # Main table
        self._table = QTableWidget(0, 7)
        self._table.setObjectName("MissingTable")
        self._table.setHorizontalHeaderLabels([
            "✓", "Typ", "XML-Datei", "Fehlender Pfad", "Gefundene Datei", "Konfidenz", "Status"
        ])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hdr_view = self._table.horizontalHeader()
        hdr_view.setSectionResizeMode(COL_SEL, QHeaderView.Fixed)
        hdr_view.setSectionResizeMode(COL_TYPE, QHeaderView.Fixed)
        hdr_view.setSectionResizeMode(COL_XML, QHeaderView.Interactive)
        hdr_view.setSectionResizeMode(COL_MISSING, QHeaderView.Stretch)
        hdr_view.setSectionResizeMode(COL_MATCH, QHeaderView.Stretch)
        hdr_view.setSectionResizeMode(COL_CONF, QHeaderView.Fixed)
        hdr_view.setSectionResizeMode(COL_STATUS, QHeaderView.Fixed)
        self._table.setColumnWidth(COL_SEL, 36)
        self._table.setColumnWidth(COL_TYPE, 60)
        self._table.setColumnWidth(COL_XML, 160)
        self._table.setColumnWidth(COL_CONF, 90)
        self._table.setColumnWidth(COL_STATUS, 80)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        self._table.doubleClicked.connect(self._manual_fix_row)
        root.addWidget(self._table, 1)

        # Bottom progress + stats
        bottom = QHBoxLayout()
        self._stats_label = QLabel("Noch keine Analyse durchgeführt.")
        self._stats_label.setObjectName("StatusLabel")
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setFixedHeight(8)
        self._progress.setVisible(False)
        bottom.addWidget(self._stats_label)
        bottom.addStretch()
        bottom.addWidget(self._progress)
        root.addSpacing(8)
        root.addLayout(bottom)

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    # ── Public API ─────────────────────────────────────────────────────────
    def set_history(self, history):
        """Register the ActionHistory for undo/redo."""
        self._history = history

    def update_index(self, index: SDCardIndex):
        self._index = index
        self._run_analysis()

    # ── Analysis ───────────────────────────────────────────────────────────
    def _run_analysis(self):
        if not self._index:
            self._stats_label.setText("Kein SD-Card Index. Bitte zuerst scannen.")
            return

        self._refs = collect_missing_refs(self._index)
        self._populate_table(self._refs)

        total = len(self._refs)
        self._stats_label.setText(
            f"{total} fehlende Referenz{'en' if total != 1 else ''} in "
            f"{self._index.total_missing_refs} XML-Dateien."
        )
        self._auto_match_btn.setEnabled(total > 0)
        self._search_folder_btn.setEnabled(total > 0)
        self._export_btn.setEnabled(total > 0)
        self._apply_btn.setEnabled(False)

    # ── Table population ───────────────────────────────────────────────────
    def _populate_table(self, refs: list[MissingRef]):
        self._table.setRowCount(0)
        for ref in refs:
            self._add_row(ref)
        self._update_apply_button()

    def _add_row(self, ref: MissingRef):
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Checkbox
        chk = QTableWidgetItem()
        chk.setCheckState(Qt.Checked)
        chk.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, COL_SEL, chk)

        # Type badge
        type_map = {"song": ("🎵", "#1E6FBB"), "kit": ("🥁", "#8E44AD"), "synth": ("🎹", "#E67E22")}
        icon, color = type_map.get(ref.xml_type, ("?", "#888888"))
        type_item = QTableWidgetItem(f"{icon} {ref.xml_type}")
        type_item.setForeground(QColor(color))
        self._table.setItem(row, COL_TYPE, type_item)

        # XML file
        self._table.setItem(row, COL_XML, QTableWidgetItem(ref.xml_file.name))

        # Missing path
        missing_item = QTableWidgetItem(ref.broken_path)
        missing_item.setForeground(QColor("#E74C3C"))
        self._table.setItem(row, COL_MISSING, missing_item)

        # Match
        self._update_match_cell(row, ref)

        # Confidence
        self._update_conf_cell(row, ref)

        # Status
        self._update_status_cell(row, ref)

        # Store ref reference
        self._table.item(row, COL_XML).setData(Qt.UserRole, ref)

    def _update_match_cell(self, row: int, ref: MissingRef):
        if ref.resolution:
            item = QTableWidgetItem(str(ref.resolution.name))
            item.setForeground(QColor("#2ECC71"))
            item.setToolTip(str(ref.resolution))
        elif ref.match_confidence == "none":
            item = QTableWidgetItem("— Kein Match —")
            item.setForeground(QColor("#888888"))
        else:
            item = QTableWidgetItem("Nicht gesucht")
            item.setForeground(QColor("#555577"))
        self._table.setItem(row, COL_MATCH, item)

    def _update_conf_cell(self, row: int, ref: MissingRef):
        conf_map = {
            "exact":       ("Exakt",    "#2ECC71"),
            "exact_multi": ("Exakt*",   "#F39C12"),
            "fuzzy":       ("Ähnlich",  "#E67E22"),
            "none":        ("Kein",     "#888888"),
            "":            ("—",        "#555555"),
        }
        text, color = conf_map.get(ref.match_confidence, ("—", "#888888"))
        item = QTableWidgetItem(text)
        item.setForeground(QColor(color))
        item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, COL_CONF, item)

    def _update_status_cell(self, row: int, ref: MissingRef):
        if ref.fixed:
            item = QTableWidgetItem("✅ Fertig")
            item.setForeground(QColor("#2ECC71"))
        elif ref.resolution:
            item = QTableWidgetItem("🔧 Bereit")
            item.setForeground(QColor("#F39C12"))
        else:
            item = QTableWidgetItem("❌ Offen")
            item.setForeground(QColor("#E74C3C"))
        item.setTextAlignment(Qt.AlignCenter)
        self._table.setItem(row, COL_STATUS, item)

    def _refresh_row(self, row: int):
        ref = self._get_ref(row)
        if ref:
            self._update_match_cell(row, ref)
            self._update_conf_cell(row, ref)
            self._update_status_cell(row, ref)

    def _get_ref(self, row: int) -> Optional[MissingRef]:
        item = self._table.item(row, COL_XML)
        return item.data(Qt.UserRole) if item else None

    # ── Auto-match ─────────────────────────────────────────────────────────
    def _run_auto_match(self):
        if not self._index or not self._refs:
            return

        self._auto_match_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._stats_label.setText("Auto-Match läuft…")

        self._worker = AutoMatchWorker(self._refs, self._index.root_path)
        self._worker.progress.connect(lambda p, m: (
            self._progress.setValue(p),
            self._stats_label.setText(m)
        ))
        self._worker.finished.connect(self._on_auto_match_done)
        self._worker.error.connect(self._on_auto_match_error)
        self._worker.start()

    def _on_auto_match_error(self, msg: str):
        self._progress.setVisible(False)
        self._auto_match_btn.setEnabled(True)
        self._stats_label.setText(f"⚠  Auto-Match Fehler: {msg}")
        QMessageBox.warning(self, "Auto-Match Fehler", msg)

    def _on_auto_match_done(self, refs):
        self._progress.setVisible(False)
        for row in range(self._table.rowCount()):
            self._refresh_row(row)
            # Rows start pre-checked (before any match is known). Only a
            # single, unambiguous filename match ("exact") is safe to
            # leave checked for one-click "Fixes anwenden" - "exact_multi"
            # (same filename exists in several places, resolved by a
            # best-guess path heuristic) and "fuzzy" (similarity match,
            # possibly a different sound entirely) must be reviewed and
            # opted into by hand, so they get unchecked here.
            ref = self._get_ref(row)
            if ref and ref.match_confidence not in ("exact", "manual"):
                chk = self._table.item(row, COL_SEL)
                if chk:
                    chk.setCheckState(Qt.Unchecked)
        matched = sum(1 for r in refs if r.match)
        total = len(refs)
        self._stats_label.setText(
            f"Auto-Match: {matched}/{total} Treffer. "
            f"Doppelklick auf Zeile für manuellen Fix."
        )
        self._auto_match_btn.setEnabled(True)
        self._update_apply_button()

    # ── Search in folder ───────────────────────────────────────────────────
    def _search_in_folder(self):
        if not self._index:
            return
        folder = QFileDialog.getExistingDirectory(self, "Ordner nach Samples durchsuchen", "")
        if not folder:
            return

        self._stats_label.setText("Durchsuche Ordner…")
        search_folder_for_missing(self._refs, Path(folder), self._index.root_path)
        for row in range(self._table.rowCount()):
            self._refresh_row(row)
        matched = sum(1 for r in self._refs if r.match)
        self._stats_label.setText(f"Ordner-Suche: {matched}/{len(self._refs)} Matches.")
        self._update_apply_button()

    # ── Manual fix ─────────────────────────────────────────────────────────
    def _manual_fix_row(self, index):
        row = index.row()
        ref = self._get_ref(row)
        if not ref or ref.fixed:
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Sample für '{ref.filename}' wählen", "",
            "Audio Files (*.wav *.aif *.aiff *.mp3 *.flac *.ogg);;All Files (*)"
        )
        if file_path:
            ref.user_choice = Path(file_path)
            ref.match_confidence = "manual"
            self._refresh_row(row)
            self._update_apply_button()

    def _context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        ref = self._get_ref(row)
        if not ref:
            return

        menu = QMenu(self)
        if not ref.fixed:
            act_fix = menu.addAction("🔧  Manuell zuweisen…")
            act_fix.triggered.connect(lambda: self._manual_fix_row(
                self._table.model().index(row, 0)))
        if ref.resolution and not ref.fixed:
            act_apply = menu.addAction("✅  Diesen Fix anwenden")
            act_apply.triggered.connect(lambda: self._apply_single(row))
        menu.addSeparator()
        act_copy = menu.addAction("📋  Pfad kopieren")
        act_copy.triggered.connect(lambda: self._copy_path(ref))
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _apply_single(self, row: int):
        ref = self._get_ref(row)
        if not ref or not ref.resolution or ref.fixed:
            return
        try:
            from ..core.file_ops import _read_xml, _write_xml
            from ..core.history import Action

            text_before, enc = _read_xml(ref.xml_file)

            sd_root = _guess_sd_root(ref.xml_file)
            try:
                new_rel = str(ref.resolution.relative_to(sd_root)).replace("\\", "/")
            except ValueError:
                new_rel = str(ref.resolution).replace("\\", "/")
            if update_xml_path(ref.xml_file, ref.broken_path, new_rel):
                ref.fixed = True
                self._refresh_row(row)
                self._stats_label.setText(f"✅  Fix angewendet: {ref.filename}")

                if self._history:
                    _path, _enc, _before = ref.xml_file, enc, text_before
                    text_after, _ = _read_xml(ref.xml_file)
                    self._history.push(Action(
                        description=f"Sample-Pfad repariert: {ref.filename}",
                        undo_fn=lambda p=_path, t=_before, e=_enc: _write_xml(p, t, e),
                        redo_fn=lambda p=_path, t=text_after, e=_enc: _write_xml(p, t, e),
                    ))
            else:
                self._stats_label.setText(f"⚠  Fix fehlgeschlagen für: {ref.filename}")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _copy_path(self, ref: MissingRef):
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(ref.broken_path)

    # ── Apply all fixes ────────────────────────────────────────────────────
    def _apply_fixes(self):
        ready = [r for r in self._refs
                 if r.resolution and not r.fixed
                 and self._is_checked(r)]
        if not ready:
            QMessageBox.information(self, "Keine Fixes", "Keine auswählbaren Fixes vorhanden.")
            return

        reply = QMessageBox.question(
            self, "Fixes anwenden",
            f"{len(ready)} XML-Dateien werden jetzt modifiziert.\n"
            "Stelle sicher, dass du vorher ein Backup erstellt hast!\n\nFortfahren?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self._apply_btn.setEnabled(False)
        self._progress.setVisible(True)

        # Capture original XML content of all affected files for undo
        if self._history:
            from ..core.file_ops import _read_xml, _write_xml
            from ..core.history import Action
            _snapshots = {}
            for _r in ready:
                if _r.xml_file not in _snapshots:
                    try:
                        _t, _e = _read_xml(_r.xml_file)
                        _snapshots[_r.xml_file] = (_t, _e)
                    except Exception as e:
                        log.warning("XML-Snapshot konnte nicht gelesen werden (%s): %s", _r.xml_file.name, e)
            # Store on self for use in _on_apply_done
            self._pending_history_snapshots = _snapshots

        self._fix_worker = ApplyFixWorker(ready)
        self._fix_worker.progress.connect(lambda p, m: (
            self._progress.setValue(p),
            self._stats_label.setText(m)
        ))
        self._fix_worker.finished.connect(self._on_apply_done)
        self._fix_worker.start()

    def _on_apply_done(self, result: dict):
        self._progress.setVisible(False)
        for row in range(self._table.rowCount()):
            self._refresh_row(row)
        self._stats_label.setText(
            f"✅  {result['fixed']} Fixes angewendet"
            + (f"  |  ⚠ {result['failed']} Fehler" if result["failed"] else "")
        )
        self._update_apply_button()

        if self._history and hasattr(self, '_pending_history_snapshots'):
            from ..core.file_ops import _read_xml, _write_xml
            from ..core.history import Action
            snaps = self._pending_history_snapshots
            afters = {}
            for path in snaps:
                try:
                    t, e = _read_xml(path)
                    afters[path] = (t, e)
                except Exception as e:
                    log.warning("XML nach Apply nicht lesbar (%s): %s", path.name, e)
            count = sum(1 for r in self._refs if r.fixed)
            def _undo_all(s=snaps):
                for p, (t, e) in s.items():
                    _write_xml(p, t, e)
            def _redo_all(a=afters):
                for p, (t, e) in a.items():
                    _write_xml(p, t, e)
            self._history.push(Action(
                description=f"{count} Sample-Pfade repariert",
                undo_fn=_undo_all,
                redo_fn=_redo_all,
            ))
            del self._pending_history_snapshots

        QMessageBox.information(
            self, "Fertig",
            f"Reparatur abgeschlossen:\n"
            f"  ✅  {result['fixed']} Pfade repariert\n"
            f"  ❌  {result['failed']} Fehler\n\n"
            "Bitte die SD-Card neu scannen um den Index zu aktualisieren."
        )
        if result["fixed"] > 0:
            self.request_rescan.emit()

    def _is_checked(self, ref: MissingRef) -> bool:
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_XML)
            if item and item.data(Qt.UserRole) is ref:
                chk = self._table.item(row, COL_SEL)
                return chk and chk.checkState() == Qt.Checked
        return True

    def _update_apply_button(self):
        ready = sum(1 for r in self._refs if r.resolution and not r.fixed)
        self._apply_btn.setEnabled(ready > 0)
        if ready > 0:
            self._apply_btn.setText(f"✅  {ready} Fixes anwenden")
        else:
            self._apply_btn.setText("✅  Fixes anwenden")

    # ── Filter ─────────────────────────────────────────────────────────────
    def _apply_filter(self):
        text = self._filter_edit.text().lower()
        combo_idx = self._filter_combo.currentIndex()

        for row in range(self._table.rowCount()):
            ref = self._get_ref(row)
            if not ref:
                continue
            show = True

            if text and text not in ref.broken_path.lower() and text not in ref.xml_file.name.lower():
                show = False

            if combo_idx == 1 and ref.xml_type != "song": show = False
            elif combo_idx == 2 and ref.xml_type != "kit": show = False
            elif combo_idx == 3 and ref.xml_type != "synth": show = False
            elif combo_idx == 4 and not ref.match: show = False
            elif combo_idx == 5 and ref.match: show = False

            self._table.setRowHidden(row, not show)

    def _toggle_select_all(self, state):
        check = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_SEL)
            if item:
                item.setCheckState(check)

    # ── Export report ──────────────────────────────────────────────────────
    def _export_report(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Report speichern", "missing_samples_report.csv",
            "CSV (*.csv);;Text (*.txt)"
        )
        if not path:
            return

        from ..core.lost_finder import build_missing_samples_csv
        csv_text = build_missing_samples_csv(self._refs)
        Path(path).write_text(csv_text, encoding="utf-8")
        self._stats_label.setText(f"Report gespeichert: {path}")

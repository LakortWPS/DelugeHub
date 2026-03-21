"""
DelugeHub — Batch Hub Module
Cross-module batch operations: rename, export, delete, normalize, tag.
"""
import shutil
import zipfile
import re
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QComboBox, QLineEdit, QCheckBox, QProgressBar, QSplitter,
    QScrollArea, QGroupBox, QTabWidget
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex


class BatchWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, items: list, operation: str, params: dict):
        super().__init__()
        self.items = items
        self.operation = operation
        self.params = params

    def run(self):
        try:
            result = self._process()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))

    def _process(self) -> dict:
        op = self.operation
        total = len(self.items)
        success = failed = 0

        for i, item in enumerate(self.items):
            pct = int((i + 1) / max(total, 1) * 100)
            self.progress.emit(pct, f"[{i+1}/{total}] {item.file_path.name}")

            try:
                if op == "rename":
                    self._do_rename(item, i)
                elif op == "delete":
                    item.file_path.unlink()
                elif op == "export":
                    self._do_export(item)
                elif op == "normalize_volume":
                    self._do_normalize(item)
                success += 1
            except Exception as e:
                failed += 1

        return {"success": success, "failed": failed, "total": total}

    def _do_rename(self, item, index: int):
        pattern: str = self.params.get("pattern", "{name}")
        new_name = pattern.replace("{name}", item.name)
        new_name = new_name.replace("{index}", str(index + 1).zfill(3))
        new_name = new_name.replace("{INDEX}", str(index + 1))
        if not new_name.lower().endswith(".xml"):
            new_name += ".XML"
        new_path = item.file_path.parent / new_name
        if not new_path.exists():
            item.file_path.rename(new_path)

    def _do_export(self, item):
        dest_dir = Path(self.params.get("dest_dir", "."))
        shutil.copy2(str(item.file_path), str(dest_dir / item.file_path.name))

    def _do_normalize(self, item):
        text = item.file_path.read_text(encoding="utf-8", errors="replace")
        new_text = re.sub(
            r'(<volume>)\s*0x[0-9A-Fa-f]+\s*(</volume>)',
            r'\g<1>0x7FFFFFFF\2',
            text
        )
        if new_text != text:
            item.file_path.write_text(new_text, encoding="utf-8")


class BatchHubModule(QWidget):
    request_rescan = Signal()

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        hdr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self._lbl("⚡  Batch Hub", "PageTitle"))
        col.addWidget(self._lbl("Batch-Operationen für Songs, Kits, Synths und Samples", "PageSubtitle"))
        hdr.addLayout(col)
        hdr.addStretch()
        root.addLayout(hdr)
        root.addSpacing(14)

        # Tabs for different content types
        tabs = QTabWidget()

        tabs.addTab(self._build_content_tab("songs"), "🎵 Songs")
        tabs.addTab(self._build_content_tab("kits"), "🥁 Kits")
        tabs.addTab(self._build_content_tab("synths"), "🎹 Synths")
        tabs.addTab(self._build_sample_tab(), "📁 Samples")
        tabs.addTab(self._build_xml_tab(), "🔧 XML Tools")

        root.addWidget(tabs, 1)

        # Progress + status
        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setVisible(False)

        self._status = QLabel("Bereit.")
        self._status.setObjectName("StatusLabel")

        root.addSpacing(8)
        root.addWidget(self._progress)
        root.addWidget(self._status)

    def _build_content_tab(self, content_type: str) -> QWidget:
        widget = QWidget()
        widget.setProperty("content_type", content_type)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        # Operation selector
        ops_frame = QFrame()
        ops_frame.setObjectName("Card")
        ops_layout = QVBoxLayout(ops_frame)
        ops_layout.setContentsMargins(12, 10, 12, 10)
        ops_layout.setSpacing(8)

        op_row = QHBoxLayout()
        op_lbl = QLabel("Operation:")
        op_lbl.setFixedWidth(100)
        op_combo = QComboBox()
        op_combo.addItems([
            "Batch Umbenennen",
            "Batch Exportieren",
            "Batch Löschen",
        ])
        if content_type in ("kits", "synths"):
            op_combo.addItem("Volumes normalisieren")

        op_row.addWidget(op_lbl)
        op_row.addWidget(op_combo)
        op_row.addStretch()
        ops_layout.addLayout(op_row)

        # Rename pattern (shown when rename selected)
        pattern_row = QHBoxLayout()
        pattern_lbl = QLabel("Muster:")
        pattern_lbl.setFixedWidth(100)
        pattern_edit = QLineEdit("{name}")
        pattern_edit.setToolTip("{name} = original, {index} = 001,002…, {INDEX} = 1,2…")
        pattern_hint = QLabel("Variablen: {name}, {index}, {INDEX}")
        pattern_hint.setStyleSheet("color: #888888; font-size: 11px;")
        pattern_row.addWidget(pattern_lbl)
        pattern_row.addWidget(pattern_edit)
        pattern_row.addWidget(pattern_hint)
        ops_layout.addLayout(pattern_row)

        def toggle_pattern(idx):
            visible = op_combo.currentText() == "Batch Umbenennen"
            pattern_edit.setVisible(visible)
            pattern_hint.setVisible(visible)

        op_combo.currentIndexChanged.connect(toggle_pattern)
        toggle_pattern(0)

        layout.addWidget(ops_frame)

        # Item list with checkboxes
        item_table = QTableWidget(0, 2)
        item_table.setHorizontalHeaderLabels(["✓ Auswählen", "Name"])
        item_table.verticalHeader().setVisible(False)
        hv = item_table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Fixed)
        hv.setSectionResizeMode(1, QHeaderView.Stretch)
        item_table.setColumnWidth(0, 40)
        item_table.setAlternatingRowColors(True)
        layout.addWidget(item_table, 1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        sel_all_btn = QPushButton("Alle auswählen")
        sel_all_btn.setObjectName("SecondaryButton")
        sel_all_btn.setFixedHeight(32)
        sel_none_btn = QPushButton("Keine")
        sel_none_btn.setObjectName("SecondaryButton")
        sel_none_btn.setFixedHeight(32)

        run_btn = QPushButton(f"⚡  Ausführen")
        run_btn.setFixedHeight(36)

        btn_row.addWidget(sel_all_btn)
        btn_row.addWidget(sel_none_btn)
        btn_row.addStretch()
        btn_row.addWidget(run_btn)
        layout.addLayout(btn_row)

        def sel_all():
            for row in range(item_table.rowCount()):
                chk = item_table.item(row, 0)
                if chk:
                    chk.setCheckState(Qt.Checked)

        def sel_none():
            for row in range(item_table.rowCount()):
                chk = item_table.item(row, 0)
                if chk:
                    chk.setCheckState(Qt.Unchecked)

        def run_batch():
            selected = []
            for row in range(item_table.rowCount()):
                chk = item_table.item(row, 0)
                data_item = item_table.item(row, 1)
                if chk and chk.checkState() == Qt.Checked and data_item:
                    selected.append(data_item.data(Qt.UserRole))
            if not selected:
                QMessageBox.information(widget, "Info", "Keine Einträge ausgewählt.")
                return
            self._run_batch(selected, op_combo.currentText(), pattern_edit.text())

        sel_all_btn.clicked.connect(sel_all)
        sel_none_btn.clicked.connect(sel_none)
        run_btn.clicked.connect(run_batch)

        # Store references for update_index
        widget._item_table = item_table
        widget._op_combo = op_combo

        return widget

    def _build_sample_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        # Batch import
        import_group = QGroupBox("Batch Import")
        import_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1E6FBB; border: 1px solid #0F3460; border-radius: 6px; margin-top: 8px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; }")
        import_layout = QVBoxLayout(import_group)
        import_layout.setContentsMargins(12, 8, 12, 8)

        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("Ordner importieren:"))
        import_folder_edit = QLineEdit()
        import_folder_edit.setPlaceholderText("Quell-Ordner mit Samples…")
        import_browse = QPushButton("…")
        import_browse.setFixedWidth(36)
        import_browse.setObjectName("SecondaryButton")
        import_row.addWidget(import_folder_edit)
        import_row.addWidget(import_browse)
        import_layout.addLayout(import_row)

        dest_row = QHBoxLayout()
        dest_row.addWidget(QLabel("Ziel auf SD-Card:"))
        dest_edit = QLineEdit("SAMPLES/Import")
        dest_row.addWidget(dest_edit)
        import_layout.addLayout(dest_row)

        import_btn = QPushButton("⬇  Samples importieren")
        import_btn.clicked.connect(lambda: self._batch_import(import_folder_edit.text(), dest_edit.text()))
        import_layout.addWidget(import_btn)

        import_browse.clicked.connect(lambda: import_folder_edit.setText(
            QFileDialog.getExistingDirectory(widget, "Quell-Ordner wählen", "") or import_folder_edit.text()
        ))

        layout.addWidget(import_group)

        # Batch export
        export_group = QGroupBox("Batch Export")
        export_group.setStyleSheet(import_group.styleSheet())
        export_layout = QVBoxLayout(export_group)
        export_layout.setContentsMargins(12, 8, 12, 8)

        export_info = QLabel("Alle genutzten Samples mit Ordnerstruktur exportieren:")
        export_info.setStyleSheet("color: #888888; font-size: 12px;")
        export_layout.addWidget(export_info)

        export_btn = QPushButton("📦  Alle Samples exportieren")
        export_btn.clicked.connect(self._batch_export_samples)
        export_layout.addWidget(export_btn)

        layout.addWidget(export_group)

        # Delete unused
        unused_group = QGroupBox("Ungenutzte Samples löschen")
        unused_group.setStyleSheet(import_group.styleSheet())
        unused_layout = QVBoxLayout(unused_group)
        unused_layout.setContentsMargins(12, 8, 12, 8)

        self._unused_count_lbl = QLabel("— ungenutzte Samples")
        self._unused_count_lbl.setStyleSheet("color: #E67E22;")
        unused_layout.addWidget(self._unused_count_lbl)

        del_unused_btn = QPushButton("🗑  Ungenutzte löschen")
        del_unused_btn.setObjectName("DangerButton")
        del_unused_btn.clicked.connect(self._delete_unused_samples)
        unused_layout.addWidget(del_unused_btn)

        layout.addWidget(unused_group)
        layout.addStretch()

        return widget

    def _build_xml_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        # Validate all XMLs
        validate_group = QGroupBox("XML Validierung")
        validate_group.setStyleSheet("QGroupBox { font-weight: bold; color: #1E6FBB; border: 1px solid #0F3460; border-radius: 6px; margin-top: 8px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; }")
        v_layout = QVBoxLayout(validate_group)
        v_layout.setContentsMargins(12, 8, 12, 8)
        v_layout.setSpacing(6)

        v_layout.addWidget(QLabel("Alle SONGS/KITS/SYNTHS XML-Dateien auf Parse-Fehler prüfen:"))

        self._validate_result = QLabel("—")
        self._validate_result.setWordWrap(True)
        self._validate_result.setStyleSheet("font-size: 12px; color: #888888;")
        v_layout.addWidget(self._validate_result)

        validate_btn = QPushButton("🔍  Alle XMLs prüfen")
        validate_btn.clicked.connect(self._validate_all_xmls)
        v_layout.addWidget(validate_btn)
        layout.addWidget(validate_group)

        # Global path find & replace
        replace_group = QGroupBox("Pfad Suchen & Ersetzen")
        replace_group.setStyleSheet(validate_group.styleSheet())
        r_layout = QVBoxLayout(replace_group)
        r_layout.setContentsMargins(12, 8, 12, 8)
        r_layout.setSpacing(6)

        r_layout.addWidget(QLabel("Pfadstring in ALLEN XML-Dateien ersetzen:"))

        find_row = QHBoxLayout()
        find_row.addWidget(QLabel("Suchen:"))
        self._find_edit = QLineEdit()
        self._find_edit.setPlaceholderText("z.B. SAMPLES/OldFolder/")
        find_row.addWidget(self._find_edit)
        r_layout.addLayout(find_row)

        repl_row = QHBoxLayout()
        repl_row.addWidget(QLabel("Ersetzen:"))
        self._replace_edit = QLineEdit()
        self._replace_edit.setPlaceholderText("z.B. SAMPLES/NewFolder/")
        repl_row.addWidget(self._replace_edit)
        r_layout.addLayout(repl_row)

        replace_btn = QPushButton("🔄  Ersetzen in allen XMLs")
        replace_btn.setObjectName("SuccessButton")
        replace_btn.clicked.connect(self._global_replace)
        r_layout.addWidget(replace_btn)
        layout.addWidget(replace_group)

        layout.addStretch()
        return widget

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    # ── Public API ─────────────────────────────────────────────────────────
    def update_index(self, index: SDCardIndex):
        self._index = index
        # Update unused count
        unused = len(index.unused_samples)
        self._unused_count_lbl.setText(f"{unused} ungenutzte Samples ({sum(s.size_mb for s in index.unused_samples):.1f} MB)")

        # Update tab tables
        tabs_widget = self.findChild(QTabWidget)
        if not tabs_widget:
            return

        content_map = {
            "songs": index.songs,
            "kits": index.kits,
            "synths": index.synths,
        }
        for i in range(tabs_widget.count() - 2):  # exclude sample + xml tabs
            tab = tabs_widget.widget(i)
            ct = tab.property("content_type")
            if ct and hasattr(tab, "_item_table"):
                table = tab._item_table
                items = content_map.get(ct, [])
                table.setRowCount(0)
                for item in items:
                    row = table.rowCount()
                    table.insertRow(row)
                    chk = QTableWidgetItem()
                    chk.setCheckState(Qt.Unchecked)
                    table.setItem(row, 0, chk)
                    name_item = QTableWidgetItem(item.name)
                    name_item.setData(Qt.UserRole, item)
                    table.setItem(row, 1, name_item)

    # ── Batch operations ───────────────────────────────────────────────────
    def _run_batch(self, items: list, operation_text: str, pattern: str = ""):
        if not items:
            return

        op_map = {
            "Batch Umbenennen": "rename",
            "Batch Exportieren": "export",
            "Batch Löschen": "delete",
            "Volumes normalisieren": "normalize_volume",
        }
        op = op_map.get(operation_text, "")
        if not op:
            return

        params = {"pattern": pattern}

        if op == "delete":
            reply = QMessageBox.warning(
                self, "Löschen bestätigen",
                f"{len(items)} Dateien löschen?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        if op == "export":
            dest = QFileDialog.getExistingDirectory(self, "Export-Zielordner", "")
            if not dest:
                return
            params["dest_dir"] = dest

        self._progress.setVisible(True)
        self._progress.setValue(0)

        self._worker = BatchWorker(items, op, params)
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._status.setText(m)))
        self._worker.finished.connect(self._on_batch_done)
        self._worker.error.connect(lambda e: QMessageBox.warning(self, "Fehler", e))
        self._worker.start()

    def _on_batch_done(self, result: dict):
        self._progress.setVisible(False)
        self._status.setText(
            f"✅  {result['success']}/{result['total']} erfolgreich"
            + (f"  |  ⚠ {result['failed']} Fehler" if result["failed"] else "")
        )
        self.request_rescan.emit()

    def _batch_import(self, source_folder: str, dest_subpath: str):
        if not self._index or not source_folder:
            return
        src = Path(source_folder)
        if not src.exists():
            QMessageBox.warning(self, "Fehler", "Quell-Ordner existiert nicht.")
            return

        dest_root = self._index.root_path / dest_subpath.replace("\\", "/").strip("/")
        dest_root.mkdir(parents=True, exist_ok=True)

        audio_exts = {".wav", ".aif", ".aiff", ".mp3", ".flac"}
        files = [f for f in src.rglob("*") if f.is_file() and f.suffix.lower() in audio_exts]

        success = 0
        for f in files:
            try:
                dest = dest_root / f.name
                if not dest.exists():
                    shutil.copy2(str(f), str(dest))
                    success += 1
            except Exception:
                pass

        self._status.setText(f"✅  {success}/{len(files)} Samples importiert nach {dest_subpath}")
        if success:
            self.request_rescan.emit()

    def _batch_export_samples(self):
        if not self._index:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Samples exportieren", "samples_export.zip", "ZIP (*.zip)"
        )
        if not dest:
            return

        samples = self._index.samples
        self._progress.setVisible(True)
        total = len(samples)

        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, s in enumerate(samples):
                    if s.file_path.exists():
                        try:
                            arcname = str(s.file_path.relative_to(self._index.root_path)).replace("\\", "/")
                            zf.write(s.file_path, arcname)
                        except Exception:
                            pass
                    self._progress.setValue(int((i + 1) / max(total, 1) * 100))

            size_mb = Path(dest).stat().st_size / (1024 * 1024)
            self._status.setText(f"✅  {total} Samples exportiert ({size_mb:.1f} MB)")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))
        finally:
            self._progress.setVisible(False)

    def _delete_unused_samples(self):
        if not self._index:
            return
        unused = self._index.unused_samples
        if not unused:
            QMessageBox.information(self, "Info", "Keine ungenutzten Samples gefunden.")
            return

        total_mb = sum(s.size_mb for s in unused)
        reply = QMessageBox.warning(
            self, "Ungenutzte löschen",
            f"{len(unused)} ungenutzte Samples ({total_mb:.1f} MB) löschen?\n\nDiese Aktion kann nicht rückgängig gemacht werden!",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        deleted = 0
        for s in unused:
            try:
                s.file_path.unlink()
                deleted += 1
            except Exception:
                pass

        self._status.setText(f"🗑  {deleted} ungenutzte Samples gelöscht.")
        self.request_rescan.emit()

    def _validate_all_xmls(self):
        if not self._index:
            return
        import xml.etree.ElementTree as ET

        errors = []
        total = 0
        for folder in ("SONGS", "KITS", "SYNTHS"):
            d = self._index.root_path / folder
            if not d.exists():
                continue
            for xml in d.rglob("*.XML"):
                total += 1
                try:
                    ET.parse(xml)
                except ET.ParseError as e:
                    errors.append(f"{xml.name}: {e}")

        if errors:
            self._validate_result.setText(
                f"⚠  {len(errors)}/{total} XML-Fehler:\n" + "\n".join(errors[:10])
            )
            self._validate_result.setStyleSheet("color: #E74C3C; font-size: 12px;")
        else:
            self._validate_result.setText(f"✅  Alle {total} XML-Dateien sind valide.")
            self._validate_result.setStyleSheet("color: #2ECC71; font-size: 12px;")

    def _global_replace(self):
        if not self._index:
            return
        find_text = self._find_edit.text()
        replace_text = self._replace_edit.text()

        if not find_text:
            QMessageBox.warning(self, "Fehler", "Bitte Suchbegriff eingeben.")
            return

        reply = QMessageBox.question(
            self, "Globales Ersetzen",
            f"'{find_text}' → '{replace_text}'\nin ALLEN XML-Dateien ersetzen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        modified = 0
        for folder in ("SONGS", "KITS", "SYNTHS"):
            d = self._index.root_path / folder
            if not d.exists():
                continue
            for xml in d.rglob("*.XML"):
                from ..core.file_ops import update_xml_path
                if update_xml_path(xml, find_text, replace_text):
                    modified += 1

        self._status.setText(f"✅  {modified} XML-Dateien aktualisiert.")
        if modified:
            self.request_rescan.emit()

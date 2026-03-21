"""
DelugeHub — Song Manager Module
Browse, rename, duplicate, delete songs. Export song packages.
"""
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QLineEdit, QSplitter, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex, Song
from ..core.file_ops import update_xml_path


COL_NAME = 0
COL_BPM  = 1
COL_TRACKS = 2
COL_MISSING = 3
COL_SIZE = 4


class SongManagerModule(QWidget):
    request_rescan = Signal()
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._songs: list[Song] = []
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self._lbl("🎵  Song Manager", "PageTitle"))
        col.addWidget(self._lbl("Songs durchsuchen, exportieren und verwalten", "PageSubtitle"))
        hdr.addLayout(col)
        hdr.addStretch()
        root.addLayout(hdr)
        root.addSpacing(14)

        # Toolbar
        tb = QFrame()
        tb.setObjectName("Card")
        tb_layout = QHBoxLayout(tb)
        tb_layout.setContentsMargins(12, 8, 12, 8)
        tb_layout.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Songs suchen…")
        self._search.textChanged.connect(self._filter)

        self._export_btn = QPushButton("📦  Exportieren")
        self._export_btn.setToolTip("Song + alle Dependencies (Samples, Kits, Synths) als Paket exportieren")
        self._export_btn.clicked.connect(self._export_selected)
        self._export_btn.setEnabled(False)

        self._rename_btn = QPushButton("✏  Umbenennen")
        self._rename_btn.setObjectName("SecondaryButton")
        self._rename_btn.clicked.connect(self._rename_selected)
        self._rename_btn.setEnabled(False)

        self._dupe_btn = QPushButton("📋  Duplizieren")
        self._dupe_btn.setObjectName("SecondaryButton")
        self._dupe_btn.clicked.connect(self._duplicate_selected)
        self._dupe_btn.setEnabled(False)

        self._delete_btn = QPushButton("🗑  Löschen")
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)

        tb_layout.addWidget(QLabel("🔎"))
        tb_layout.addWidget(self._search, 1)
        tb_layout.addWidget(self._export_btn)
        tb_layout.addWidget(self._rename_btn)
        tb_layout.addWidget(self._dupe_btn)
        tb_layout.addWidget(self._delete_btn)
        root.addWidget(tb)
        root.addSpacing(8)

        # Splitter: table | detail
        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Song Name", "BPM", "Tracks", "Fehlend", "Größe"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(COL_NAME, QHeaderView.Stretch)
        hv.setSectionResizeMode(COL_BPM, QHeaderView.Interactive)
        hv.setSectionResizeMode(COL_TRACKS, QHeaderView.Interactive)
        hv.setSectionResizeMode(COL_MISSING, QHeaderView.Interactive)
        hv.setSectionResizeMode(COL_SIZE, QHeaderView.Interactive)
        self._table.setColumnWidth(COL_BPM, 65)
        self._table.setColumnWidth(COL_TRACKS, 65)
        self._table.setColumnWidth(COL_MISSING, 80)
        self._table.setColumnWidth(COL_SIZE, 75)
        self._table.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self._table)

        # Detail panel
        detail = QFrame()
        detail.setObjectName("Card")
        detail.setMinimumWidth(220)
        detail.setMaximumWidth(280)
        d_layout = QVBoxLayout(detail)
        d_layout.setContentsMargins(14, 14, 14, 14)
        d_layout.setSpacing(8)

        d_layout.addWidget(self._lbl("Song Details", "SectionTitle"))
        self._detail_name = QLabel("—")
        self._detail_name.setWordWrap(True)
        self._detail_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        d_layout.addWidget(self._detail_name)

        self._detail_info = QLabel("—")
        self._detail_info.setWordWrap(True)
        self._detail_info.setStyleSheet("color: #888888; font-size: 12px;")
        d_layout.addWidget(self._detail_info)

        d_layout.addSpacing(8)
        d_layout.addWidget(self._lbl("Sample Referenzen", "SectionTitle"))
        self._ref_tree = QTreeWidget()
        self._ref_tree.setHeaderHidden(True)
        self._ref_tree.setMaximumHeight(200)
        d_layout.addWidget(self._ref_tree)

        d_layout.addStretch()

        if_missing_btn = QPushButton("🔍  Fehlende reparieren")
        if_missing_btn.setObjectName("DangerButton")
        if_missing_btn.clicked.connect(lambda: self.navigate_to.emit("lost_sample_finder"))
        d_layout.addWidget(if_missing_btn)

        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        root.addWidget(splitter, 1)

        self._status = QLabel("—")
        self._status.setObjectName("StatusLabel")
        root.addSpacing(6)
        root.addWidget(self._status)

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    def update_index(self, index: SDCardIndex):
        self._index = index
        self._songs = index.songs
        self._populate_table(self._songs)
        self._status.setText(f"{len(self._songs)} Songs  •  {sum(len(s.missing_samples) for s in self._songs)} fehlende Referenzen")

    def _populate_table(self, songs: list[Song]):
        self._table.setRowCount(0)
        for s in songs:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(s.name)
            name_item.setData(Qt.UserRole, s)
            self._table.setItem(row, COL_NAME, name_item)

            bpm_str = f"{s.bpm:.0f}" if s.bpm else "—"
            self._table.setItem(row, COL_BPM, QTableWidgetItem(bpm_str))

            self._table.setItem(row, COL_TRACKS, QTableWidgetItem(str(s.track_count)))

            missing_item = QTableWidgetItem(str(len(s.missing_samples)))
            if s.has_missing_samples:
                missing_item.setForeground(QColor("#E74C3C"))
            else:
                missing_item.setForeground(QColor("#2ECC71"))
            self._table.setItem(row, COL_MISSING, missing_item)

            try:
                size_kb = s.file_path.stat().st_size / 1024
                size_str = f"{size_kb:.0f} KB"
            except Exception:
                size_str = "—"
            self._table.setItem(row, COL_SIZE, QTableWidgetItem(size_str))

    def _filter(self):
        text = self._search.text().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_NAME)
            self._table.setRowHidden(row, text != "" and item and text not in item.text().lower())

    def _selected_song(self) -> Optional[Song]:
        rows = self._table.selectedItems()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), COL_NAME)
        return item.data(Qt.UserRole) if item else None

    def _on_selection(self):
        song = self._selected_song()
        has = song is not None
        self._export_btn.setEnabled(has)
        self._rename_btn.setEnabled(has)
        self._dupe_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)
        if song:
            self._show_detail(song)

    def _show_detail(self, song: Song):
        self._detail_name.setText(song.name)
        bpm_str = f"{song.bpm:.1f} BPM" if song.bpm else ""
        ts = f"{song.time_signature_numerator}/{song.time_signature_denominator}"
        info = f"BPM: {bpm_str}\nTakt: {ts}\nTracks: {song.track_count}\n"
        info += f"Samples: {len(song.sample_refs)}\n"
        info += f"Fehlend: {len(song.missing_samples)}"
        self._detail_info.setText(info)

        self._ref_tree.clear()
        ok_item = QTreeWidgetItem(["✅ Vorhanden"])
        miss_item = QTreeWidgetItem(["❌ Fehlend"])
        ok_item.setForeground(0, QColor("#2ECC71"))
        miss_item.setForeground(0, QColor("#E74C3C"))

        for ref in song.sample_refs:
            child = QTreeWidgetItem([ref.path.split("/")[-1]])
            child.setToolTip(0, ref.path)
            if ref.exists:
                ok_item.addChild(child)
            else:
                miss_item.addChild(child)

        if ok_item.childCount():
            self._ref_tree.addTopLevelItem(ok_item)
            ok_item.setExpanded(ok_item.childCount() <= 10)
        if miss_item.childCount():
            self._ref_tree.addTopLevelItem(miss_item)
            miss_item.setExpanded(True)

    def _rename_selected(self):
        song = self._selected_song()
        if not song:
            return
        new_name, ok = QInputDialog.getText(
            self, "Song umbenennen", "Neuer Name:", text=song.name
        )
        if not ok or not new_name.strip() or new_name == song.name:
            return

        # Rename the XML file
        new_path = song.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei mit diesem Namen existiert bereits.")
            return
        try:
            song.file_path.rename(new_path)
            self._status.setText(f"✅  Song umbenannt → {new_name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _duplicate_selected(self):
        song = self._selected_song()
        if not song:
            return
        new_name, ok = QInputDialog.getText(
            self, "Song duplizieren", "Name der Kopie:", text=f"{song.name}_copy"
        )
        if not ok or not new_name.strip():
            return

        new_path = song.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        try:
            shutil.copy2(str(song.file_path), str(new_path))
            self._status.setText(f"✅  Dupliziert → {new_name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _delete_selected(self):
        song = self._selected_song()
        if not song:
            return
        reply = QMessageBox.question(
            self, "Song löschen",
            f"'{song.name}' wirklich löschen?\n(Nur die Song-Datei, keine Samples)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        try:
            song.file_path.unlink()
            self._status.setText(f"🗑  Gelöscht: {song.name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _export_selected(self):
        song = self._selected_song()
        if not song or not self._index:
            return

        dest, _ = QFileDialog.getSaveFileName(
            self, f"Song '{song.name}' exportieren", f"{song.name}_package.zip",
            "ZIP Archive (*.zip)"
        )
        if not dest:
            return

        try:
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                # Song XML
                zf.write(song.file_path, f"SONGS/{song.file_path.name}")
                # All referenced samples that exist
                for ref in song.sample_refs:
                    if ref.exists and ref.abs_path:
                        try:
                            arcname = str(ref.abs_path.relative_to(self._index.root_path)).replace("\\", "/")
                            zf.write(ref.abs_path, arcname)
                        except Exception:
                            pass

            size_mb = Path(dest).stat().st_size / (1024 * 1024)
            self._status.setText(f"✅  Exportiert: {Path(dest).name} ({size_mb:.1f} MB)")
        except Exception as e:
            QMessageBox.warning(self, "Export-Fehler", str(e))

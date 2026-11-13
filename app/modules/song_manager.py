"""
DelugeHub — Song Manager Module
Browse, rename, duplicate, delete songs. Export song packages.
"""
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QLineEdit, QSplitter, QTreeWidget, QTreeWidgetItem,
    QDialog, QDialogButtonBox, QCheckBox, QScrollArea, QProgressDialog,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex, Song
from ..core.file_ops import update_xml_path
from ..core.staging import StagingStore, PendingChange, ChangeType
from ..core.volume_utils import vol_to_display, display_to_vol
from ..core.xml_parser import build_pack_plan, pack_target_rejected, song_needs_newer_firmware

log = logging.getLogger(__name__)

COL_NAME = 0
COL_BPM  = 1
COL_TRACKS = 2
COL_MISSING = 3
COL_SIZE = 4
COL_FW = 5


class _PackCopyWorker(QThread):
    """Copy a pack into another folder. The source card is never written."""
    progress = Signal(int, str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, files, dest: Path):
        super().__init__()
        self._files = list(files)
        self._dest = dest
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        copied = 0
        try:
            total = max(len(self._files), 1)
            for index, item in enumerate(self._files):
                if self._cancel:
                    self.succeeded.emit(
                        f"Abgebrochen — {copied} Dateien liegen schon im Ziel. Quelle unverändert."
                    )
                    return
                target = self._dest / item.rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item.abs_path), str(target))
                copied += 1
                self.progress.emit(int((index + 1) / total * 100), item.rel_path)
            self.succeeded.emit(f"Set gepackt: {copied} Dateien. Quelle unverändert.")
        except Exception as e:
            log.error("Set packen fehlgeschlagen: %s", e)
            self.failed.emit(str(e))


class SongManagerModule(QWidget):
    request_rescan = Signal()
    navigate_to = Signal(str)

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._songs: list[Song] = []
        self._history = None
        self._staging: Optional[StagingStore] = None
        self._pack_worker = None
        self._pack_progress = None
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
        tb_layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Songs suchen…")
        self._search.textChanged.connect(self._filter)

        self._export_btn = QPushButton("📦 Exportieren")
        self._export_btn.setObjectName("SecondaryButton")
        self._export_btn.setToolTip("Song + alle Dependencies (Samples, Kits, Synths) als Paket exportieren")
        self._export_btn.clicked.connect(self._export_selected)
        self._export_btn.setEnabled(False)

        self._pack_btn = QPushButton("Set packen")
        self._pack_btn.setObjectName("SecondaryButton")
        self._pack_btn.setToolTip(
            "Ausgewählte Songs plus nur die Kits, Synths und Samples, die sie brauchen, "
            "in einen anderen Ordner kopieren. Die Quellkarte bleibt unverändert."
        )
        self._pack_btn.clicked.connect(self._pack_set)
        self._pack_btn.setEnabled(False)

        self._rename_btn = QPushButton("✏ Umbenennen")
        self._rename_btn.setObjectName("SecondaryButton")
        self._rename_btn.clicked.connect(self._rename_selected)
        self._rename_btn.setEnabled(False)

        self._dupe_btn = QPushButton("📋 Duplizieren")
        self._dupe_btn.setObjectName("SecondaryButton")
        self._dupe_btn.clicked.connect(self._duplicate_selected)
        self._dupe_btn.setEnabled(False)

        self._cap_master_btn = QPushButton("⬇ Master")
        self._cap_master_btn.setObjectName("SecondaryButton")
        self._cap_master_btn.setToolTip(
            "Song-Master-Volume (songParams) auf eine Maximallautstärke begrenzen.\n"
            "Werte über dem Limit werden gesenkt, Werte darunter bleiben unverändert."
        )
        self._cap_master_btn.clicked.connect(self._cap_song_master)
        self._cap_master_btn.setEnabled(False)

        self._cap_clips_btn = QPushButton("⬇ Clips")
        self._cap_clips_btn.setObjectName("SecondaryButton")
        self._cap_clips_btn.setToolTip(
            "Alle Clip-Volumes (kitParams/synthParams) auf eine Maximallautstärke begrenzen.\n"
            "Werte über dem Limit werden gesenkt — interne Sound-Volumes bleiben unberührt."
        )
        self._cap_clips_btn.clicked.connect(self._cap_clip_volumes)
        self._cap_clips_btn.setEnabled(False)

        self._delete_btn = QPushButton("🗑")
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.setToolTip("Ausgewählten Song löschen")
        self._delete_btn.setFixedWidth(34)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)

        tb_layout.addWidget(QLabel("🔎"))
        tb_layout.addWidget(self._search, 1)
        tb_layout.addWidget(self._export_btn)
        tb_layout.addWidget(self._pack_btn)
        tb_layout.addWidget(self._rename_btn)
        tb_layout.addWidget(self._dupe_btn)
        tb_layout.addWidget(self._cap_master_btn)
        tb_layout.addWidget(self._cap_clips_btn)
        tb_layout.addWidget(self._delete_btn)
        root.addWidget(tb)
        root.addSpacing(8)

        # Splitter: table | detail
        splitter = QSplitter(Qt.Horizontal)

        self._table = QTableWidget(0, 6)
        self._table.setHorizontalHeaderLabels(
            ["Song Name", "BPM", "Tracks", "Fehlend", "Größe", "Firmware"]
        )
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
        hv.setSectionResizeMode(COL_FW, QHeaderView.Interactive)
        self._table.setColumnWidth(COL_BPM, 65)
        self._table.setColumnWidth(COL_TRACKS, 65)
        self._table.setColumnWidth(COL_MISSING, 80)
        self._table.setColumnWidth(COL_SIZE, 75)
        self._table.setColumnWidth(COL_FW, 80)
        self._table.itemSelectionChanged.connect(self._on_selection)
        splitter.addWidget(self._table)

        # Detail panel
        detail = QFrame()
        detail.setObjectName("Card")
        detail.setMinimumWidth(220)
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

        if_missing_btn = QPushButton("🔍 Fehlende reparieren")
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

        from ..widgets.pending_panel import PendingPanel
        self._pending_panel = PendingPanel(
            "song_manager", StagingStore(),
            rescan_fn=self.request_rescan.emit
        )
        root.addWidget(self._pending_panel)

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    def set_history(self, history):
        self._history = history

    def set_staging(self, staging: StagingStore):
        self._staging = staging
        if hasattr(self, '_pending_panel'):
            self._pending_panel._staging = staging
            self._pending_panel.refresh()

    def update_index(self, index: SDCardIndex):
        self._index = index
        self._songs = index.songs
        self._populate_table(self._songs)
        self._pack_btn.setEnabled(bool(self._songs))
        self._status.setText(f"{len(self._songs)} Songs  •  {sum(len(s.missing_samples) for s in self._songs)} fehlende Referenzen")

    def select_by_path(self, file_path) -> bool:
        """Select the table row whose Song.file_path matches. Returns True if found."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, COL_NAME)
            song = item.data(Qt.UserRole) if item else None
            if song is not None and song.file_path == file_path:
                self._table.setRowHidden(row, False)
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                return True
        return False

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
            except Exception as e:
                log.debug("Dateigröße nicht lesbar für %s: %s", s.file_path.name, e)
                size_str = "—"
            self._table.setItem(row, COL_SIZE, QTableWidgetItem(size_str))
            self._table.setItem(row, COL_FW, self._firmware_item(s))

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
        self._cap_master_btn.setEnabled(has)
        self._cap_clips_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)
        if song:
            self._show_detail(song)

    def _show_detail(self, song: Song):
        self._detail_name.setText(song.name)
        bpm_str = f"{song.bpm:.1f} BPM" if song.bpm else ""
        ts = f"{song.time_signature_numerator}/{song.time_signature_denominator}"
        info = f"BPM: {bpm_str}\nTakt: {ts}\nTracks: {song.track_count}\n"
        info += f"Samples: {len(song.sample_refs)}\n"
        info += f"Fehlend: {len(song.missing_samples)}\n"
        info += f"Firmware: {song.firmware_version or '—'}\n"
        info += f"Früheste Firmware: {song.earliest_compatible or '—'}"
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

    def _firmware_item(self, song: Song) -> QTableWidgetItem:
        item = QTableWidgetItem("")
        if not self._index or not song.earliest_compatible:
            return item
        others = []
        for other in self._index.songs:
            if other.file_path != song.file_path and other.earliest_compatible:
                others.append(other.earliest_compatible)
        for kit in self._index.kits:
            if kit.earliest_compatible:
                others.append(kit.earliest_compatible)
        for synth in self._index.synths:
            if synth.earliest_compatible:
                others.append(synth.earliest_compatible)
        base = song_needs_newer_firmware(song.earliest_compatible, others)
        if not base:
            return item
        item = QTableWidgetItem("neuer")
        item.setToolTip(f"Song braucht {song.earliest_compatible}, Karte sonst bis {base}")
        return item

    def _pack_set(self):
        if not self._index or not self._index.songs:
            self._status.setText("Keine Songs im Index.")
            return
        if self._pack_worker and self._pack_worker.isRunning():
            self._status.setText("Set wird noch kopiert…")
            return
        selected = self._ask_pack_songs()
        if not selected:
            return
        plan = build_pack_plan(self._index, selected)
        if not plan.files:
            self._status.setText("Nichts zu packen.")
            return
        if not self._confirm_pack(plan):
            return
        dest = QFileDialog.getExistingDirectory(self, "Zielordner für das Set", "")
        if not dest:
            return
        dest_path = Path(dest)
        if pack_target_rejected(self._index.root_path, dest_path):
            self._status.setText("Ziel abgelehnt: der Ordner liegt auf der Quellkarte oder enthält sie.")
            return
        self._start_pack_copy(plan, dest_path)

    def _ask_pack_songs(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Set packen")
        dlg.resize(420, 480)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Songs für das Set:"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        current = self._selected_song()
        boxes = []
        for song in self._index.songs:
            box = QCheckBox(song.name)
            box.setChecked(current is not None and song.file_path == current.file_path)
            inner_layout.addWidget(box)
            boxes.append((box, song))
        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Weiter")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() != QDialog.Accepted:
            return None
        chosen = [song for box, song in boxes if box.isChecked()]
        if not chosen:
            self._status.setText("Keine Songs ausgewählt.")
            return None
        return chosen

    def _confirm_pack(self, plan) -> bool:
        text = (
            f"{plan.count_kind('song')} Songs, {plan.count_kind('kit')} Kits, "
            f"{plan.count_kind('synth')} Synths, {plan.count_kind('sample')} Samples\n"
            f"{plan.total_bytes / (1024 * 1024):.1f} MB"
        )
        details = []
        if plan.missing:
            details.append("Fehlende Samples:")
            details.extend(plan.missing)
        if plan.unresolved_presets:
            details.append("Nicht aufgelöste Presets:")
            details.extend(plan.unresolved_presets)
        box = QMessageBox(self)
        box.setWindowTitle("Set packen")
        box.setText(text)
        if details:
            box.setDetailedText("\n".join(details))
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.button(QMessageBox.Ok).setText("Kopieren")
        box.button(QMessageBox.Cancel).setText("Abbrechen")
        return box.exec() == QMessageBox.Ok

    def _start_pack_copy(self, plan, dest: Path):
        self._pack_btn.setEnabled(False)
        progress = QProgressDialog("Set wird kopiert…", "Abbrechen", 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        self._pack_progress = progress
        worker = _PackCopyWorker(plan.files, dest)
        self._pack_worker = worker
        worker.progress.connect(lambda value, name: (
            progress.setValue(value),
            progress.setLabelText(name),
        ))
        progress.canceled.connect(worker.cancel)
        worker.succeeded.connect(self._on_pack_done)
        worker.failed.connect(self._on_pack_failed)
        worker.start()

    def _on_pack_done(self, message: str):
        if self._pack_progress is not None:
            self._pack_progress.close()
        self._pack_btn.setEnabled(bool(self._songs))
        self._status.setText(message)

    def _on_pack_failed(self, message: str):
        if self._pack_progress is not None:
            self._pack_progress.close()
        self._pack_btn.setEnabled(bool(self._songs))
        self._status.setText(f"Packen fehlgeschlagen: {message}. Quelle unverändert.")

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
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.RENAME,
                file_path=song.file_path,
                source_module="song_manager",
                new_name=f"{new_name.strip()}.XML",
            ))
            self._status.setText(f"⏳  Umbenennen vorgemerkt: {song.name} → {new_name}")
            self._pending_panel.refresh()
        else:
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
            f"'{song.name}' wirklich löschen?\n(Erst gespeichert wenn du 'Speichern' drückst)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.DELETE,
                file_path=song.file_path,
                source_module="song_manager",
            ))
            self._status.setText(f"⏳  Zum Löschen vorgemerkt: {song.name}")
            self._pending_panel.refresh()
        else:
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
                        except Exception as e:
                            log.warning("Sample konnte nicht exportiert werden (%s): %s", ref.abs_path.name if ref.abs_path else '?', e)

            size_mb = Path(dest).stat().st_size / (1024 * 1024)
            self._status.setText(f"✅  Exportiert: {Path(dest).name} ({size_mb:.1f} MB)")
        except Exception as e:
            QMessageBox.warning(self, "Export-Fehler", str(e))

    # ── Volume-Cap Helpers (delegiert an core.volume_utils) ───────────────
    _vol_to_display = staticmethod(vol_to_display)
    _display_to_vol = staticmethod(display_to_vol)

    def _cap_song_master(self):
        song = self._selected_song()
        if not song:
            return

        threshold, ok = QInputDialog.getInt(
            self, "Song-Master begrenzen",
            "Maximale Lautstärke für Song-Master (0 – 50):",
            40, 0, 50, 1
        )
        if not ok:
            return

        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(song.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Song-XML konnte nicht geparst werden.")
            return

        sp = root.find("songParams")
        if sp is None:
            self._status.setText("ℹ  Kein <songParams> im Song gefunden.")
            return

        vol_str = sp.get("volume", "").strip()
        vol_format = "attr"
        if not vol_str:
            vol_elem = sp.find("volume")
            if vol_elem is not None:
                vol_str = (vol_elem.text or "").strip()
                vol_format = "elem"

        if not vol_str:
            self._status.setText("ℹ  Kein Volume-Wert in songParams gefunden.")
            return

        current_display = self._vol_to_display(vol_str)
        if current_display <= threshold:
            self._status.setText(
                f"ℹ  Song-Master liegt bei {current_display:.1f}/50 — kein Cap nötig."
            )
            return

        new_hex = self._display_to_vol(threshold)
        text, enc = _read_xml(song.file_path)

        clips_pos = text.find('<sessionClips>')
        pre_block  = text[:clips_pos] if clips_pos >= 0 else text
        post_block = text[clips_pos:] if clips_pos >= 0 else ""

        if vol_format == "attr":
            old_tag, new_tag = f'volume="{vol_str}"', f'volume="{new_hex}"'
        else:
            old_tag = f'<volume>{vol_str}</volume>'
            new_tag = f'<volume>{new_hex}</volume>'

        new_pre = pre_block.replace(old_tag, new_tag, 1)
        if new_pre == pre_block:
            self._status.setText("ℹ  Volume-Wert konnte nicht im XML gefunden werden.")
            return

        new_text = new_pre + post_block
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=song.file_path,
                source_module="song_manager",
                new_content=new_text,
                encoding=enc,
            ))
            self._status.setText(
                f"⏳  Vorgemerkt: Song-Master {current_display:.1f}/50 → {threshold}/50."
            )
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(song.file_path, new_text, enc)
                self._status.setText(
                    f"✅  Song-Master auf max. {threshold}/50 begrenzt."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _cap_clip_volumes(self):
        """Begrenzt alle Clip-Volumes (kitParams/synthParams) im ausgewählten Song."""
        import re
        song = self._selected_song()
        if not song:
            return

        threshold, ok = QInputDialog.getInt(
            self, "Clip-Volumes begrenzen",
            "Maximale Lautstärke für alle Clips (0 – 50):",
            40, 0, 50, 1
        )
        if not ok:
            return

        from ..core.file_ops import _read_xml, _write_xml

        text, enc = _read_xml(song.file_path)

        def cap_vol(m):
            if self._vol_to_display(m.group(2)) > threshold:
                return m.group(1) + f'volume="{self._display_to_vol(threshold)}"'
            return m.group(0)

        new_text = re.sub(
            r'(<(?:kitParams|synthParams)\b[^>]*)volume="(0x[0-9A-Fa-f]+)"',
            cap_vol,
            text,
        )

        if new_text == text:
            self._status.setText("ℹ  Alle Clip-Volumes bereits im Limit.")
            return

        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=song.file_path,
                source_module="song_manager",
                new_content=new_text,
                              encoding=enc,
            ))
            self._status.setText(f"⏳  Vorgemerkt: Clip-Volumes → max. {threshold}/50.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(song.file_path, new_text, enc)
                self._status.setText(f"✅  Clip-Volumes auf max. {threshold}/50 begrenzt.")
                self.request_rescan.emit()
            except Exception as e:
                log.warning("_cap_clip_volumes fehlgeschlagen: %s", e)
                QMessageBox.warning(self, "Fehler", str(e))

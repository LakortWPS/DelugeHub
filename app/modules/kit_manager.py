"""
DelugeHub — Kit Manager Module
Browse kits, view pad assignments, re-assign samples, normalize and cap volumes.
"""
import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QAbstractItemView, QFileDialog, QInputDialog, QMessageBox,
    QLineEdit, QSplitter, QGridLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex, Kit
from ..core.sd_scanner import AUDIO_EXTENSIONS
from ..core.staging import StagingStore, PendingChange, ChangeType
from ..core.volume_utils import (
    vol_to_display, display_to_vol, vol_to_amp, amp_to_vol,
    apply_sequential_replacements,
)

log = logging.getLogger(__name__)

_PAD_AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff"}


def pad_preview_enabled(path_exists, suffix, available, supports_all_formats) -> bool:
    """Same play rule as the sample manager: file on disk, player up, format ok."""
    ext = (suffix or "").lower()
    if not path_exists or not available:
        return False
    if supports_all_formats:
        return ext in AUDIO_EXTENSIONS
    return ext == ".wav"


class PadGridFrame(QFrame):
    """4×4 pad grid. Accepts a folder drop, ignores loose files."""
    folder_dropped = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("Card")
        self.setAcceptDrops(True)

    def _directory_url(self, event):
        mime = event.mimeData()
        if mime is None or not mime.hasUrls():
            return None
        urls = mime.urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        if path.is_dir():
            return str(path)
        return None

    def dragEnterEvent(self, event):
        if self._directory_url(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._directory_url(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        folder = self._directory_url(event)
        if not folder:
            event.ignore()
            return
        self.folder_dropped.emit(folder)
        event.acceptProposedAction()


class PadWidget(QFrame):
    """A single pad cell in the kit grid."""
    clicked = Signal(int)

    def __init__(self, pad_number: int):
        super().__init__()
        self._pad_number = pad_number
        self.setObjectName("Card")
        self.setFixedSize(88, 72)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        num_lbl = QLabel(str(pad_number + 1))
        num_lbl.setAlignment(Qt.AlignRight)
        num_lbl.setStyleSheet("color: #555577; font-size: 10px;")

        self._name_lbl = QLabel("—")
        self._name_lbl.setAlignment(Qt.AlignCenter)
        self._name_lbl.setWordWrap(True)
        self._name_lbl.setStyleSheet("font-size: 10px; color: #AAAAAA;")

        layout.addWidget(num_lbl)
        layout.addWidget(self._name_lbl, 1)

    def set_sample(self, name: str, has_file: bool = True):
        short = name[:10] + "…" if len(name) > 10 else name
        self._name_lbl.setText(short)
        self._name_lbl.setToolTip(name)
        if has_file:
            self.setObjectName("CardAccent")
        else:
            self.setObjectName("CardError")
        self.style().unpolish(self)
        self.style().polish(self)

    def _grid_frame(self):
        parent = self.parent()
        while parent is not None and not isinstance(parent, PadGridFrame):
            parent = parent.parent()
        return parent

    def dragEnterEvent(self, event):
        frame = self._grid_frame()
        if frame is not None and frame._directory_url(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        frame = self._grid_frame()
        if frame is None:
            event.ignore()
            return
        frame.dropEvent(event)

    def mousePressEvent(self, event):
        self.clicked.emit(self._pad_number)
        super().mousePressEvent(event)


class KitManagerModule(QWidget):
    request_rescan = Signal()
    open_path = Signal(str, object)

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._kits: list[Kit] = []
        self._current_kit: Optional[Kit] = None
        self._pads: list[PadWidget] = []
        self._history = None
        self._staging: Optional[StagingStore] = None
        from .sample_manager import AudioPlayer
        self._player = AudioPlayer()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        hdr = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(4)
        col.addWidget(self._lbl("🥁  Kit Manager", "PageTitle"))
        col.addWidget(self._lbl("Kits durchsuchen, Pad-Zuweisungen bearbeiten, Volumes normalisieren", "PageSubtitle"))
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
        self._search.setPlaceholderText("Kits suchen…")
        self._search.textChanged.connect(self._filter)

        self._rename_btn = QPushButton("✏ Umbenennen")
        self._rename_btn.setObjectName("SecondaryButton")
        self._rename_btn.clicked.connect(self._rename_selected)
        self._rename_btn.setEnabled(False)

        self._dupe_btn = QPushButton("📋 Duplizieren")
        self._dupe_btn.setObjectName("SecondaryButton")
        self._dupe_btn.clicked.connect(self._duplicate_selected)
        self._dupe_btn.setEnabled(False)

        self._norm_btn = QPushButton("🔊 Normalisieren")
        self._norm_btn.setObjectName("SecondaryButton")
        self._norm_btn.setToolTip(
            "WAV-Dateien analysieren (RMS) und Pad-Volumes angleichen,\n"
            "sodass alle Pads gleich laut klingen."
        )
        self._norm_btn.clicked.connect(self._normalize_volumes)
        self._norm_btn.setEnabled(False)

        self._cap_master_btn = QPushButton("⬇ Master")
        self._cap_master_btn.setObjectName("SecondaryButton")
        self._cap_master_btn.setToolTip(
            "Kit-Master-Volume auf eine Maximallautstärke begrenzen.\n"
            "Werte über dem Limit werden gesenkt, Werte darunter bleiben unverändert."
        )
        self._cap_master_btn.clicked.connect(self._cap_kit_master)
        self._cap_master_btn.setEnabled(False)

        self._cap_pads_btn = QPushButton("⬇ Pads")
        self._cap_pads_btn.setObjectName("SecondaryButton")
        self._cap_pads_btn.setToolTip(
            "Alle Pad-Volumes auf eine Maximallautstärke begrenzen.\n"
            "Werte über dem Limit werden gesenkt, Werte darunter bleiben unverändert."
        )
        self._cap_pads_btn.clicked.connect(self._cap_pad_volumes)
        self._cap_pads_btn.setEnabled(False)

        self._import_btn = QPushButton("⬇ Importieren")
        self._import_btn.setObjectName("SecondaryButton")
        self._import_btn.setToolTip("Kit-XML aus Dateisystem importieren")
        self._import_btn.clicked.connect(self._import_kit)

        self._delete_btn = QPushButton("🗑")
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.setToolTip("Ausgewähltes Kit löschen")
        self._delete_btn.setFixedWidth(34)
        self._delete_btn.clicked.connect(self._delete_selected)
        self._delete_btn.setEnabled(False)

        tb_layout.addWidget(QLabel("🔎"))
        tb_layout.addWidget(self._search, 1)
        tb_layout.addWidget(self._rename_btn)
        tb_layout.addWidget(self._dupe_btn)
        tb_layout.addWidget(self._norm_btn)
        tb_layout.addWidget(self._cap_master_btn)
        tb_layout.addWidget(self._cap_pads_btn)
        tb_layout.addWidget(self._import_btn)
        tb_layout.addWidget(self._delete_btn)
        root.addWidget(tb)
        root.addSpacing(8)

        # Splitter: kit list | pad grid + detail
        splitter = QSplitter(Qt.Horizontal)

        # Kit list table
        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["Kit Name", "Pads", "Fehlend"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        hv.setSectionResizeMode(1, QHeaderView.Interactive)
        hv.setSectionResizeMode(2, QHeaderView.Interactive)
        self._table.setColumnWidth(1, 55)
        self._table.setColumnWidth(2, 80)
        self._table.setMinimumWidth(240)
        self._table.itemSelectionChanged.connect(self._on_kit_selected)
        splitter.addWidget(self._table)

        # Right panel: pad grid + pad detail
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(12)

        # Pad grid (4x4 = 16 pads). Drops land here, not on the rest of the page.
        grid_frame = PadGridFrame()
        grid_frame.folder_dropped.connect(self._on_folder_dropped)
        grid_layout_outer = QVBoxLayout(grid_frame)
        grid_layout_outer.setContentsMargins(12, 12, 12, 12)

        self._kit_title = QLabel("Kein Kit ausgewählt")
        self._kit_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        grid_layout_outer.addWidget(self._kit_title)

        grid_container = QWidget()
        self._grid_layout = QGridLayout(grid_container)
        self._grid_layout.setSpacing(6)

        for i in range(16):
            pad = PadWidget(i)
            pad.clicked.connect(self._on_pad_click)
            self._pads.append(pad)
            row, col = divmod(i, 4)
            grid_row = 3 - row
            self._grid_layout.addWidget(pad, grid_row, col)

        grid_layout_outer.addWidget(grid_container)
        right_layout.addWidget(grid_frame)

        # Pad detail
        self._pad_detail = QFrame()
        self._pad_detail.setObjectName("Card")
        pd_layout = QVBoxLayout(self._pad_detail)
        pd_layout.setContentsMargins(12, 12, 12, 12)
        pd_layout.setSpacing(6)

        pd_layout.addWidget(self._lbl("Pad Details", "SectionTitle"))
        self._pad_info = QLabel("Klicke auf ein Pad")
        self._pad_info.setStyleSheet("color: #888888; font-size: 12px;")
        self._pad_info.setWordWrap(True)

        self._reassign_btn = QPushButton("🎵  Sample neu zuweisen")
        self._reassign_btn.setEnabled(False)
        self._reassign_btn.clicked.connect(self._reassign_pad)

        self._show_sample_btn = QPushButton("Im Sample Manager zeigen")
        self._show_sample_btn.setObjectName("SecondaryButton")
        self._show_sample_btn.setEnabled(False)
        self._show_sample_btn.clicked.connect(self._show_pad_sample)

        self._listen_btn = QPushButton("▶ Anhören")
        self._listen_btn.setEnabled(False)
        self._listen_btn.clicked.connect(self._listen_pad)

        self._listen_stop_btn = QPushButton("Stop")
        self._listen_stop_btn.setObjectName("SecondaryButton")
        self._listen_stop_btn.clicked.connect(self._player.stop)
        if not self._player.available:
            self._listen_btn.setToolTip("sounddevice nicht installiert — pip install sounddevice")

        listen_row = QHBoxLayout()
        listen_row.addWidget(self._listen_btn)
        listen_row.addWidget(self._listen_stop_btn)

        pd_layout.addWidget(self._pad_info)
        pd_layout.addWidget(self._reassign_btn)
        pd_layout.addWidget(self._show_sample_btn)
        pd_layout.addLayout(listen_row)

        right_layout.addWidget(self._pad_detail)
        right_layout.addStretch()

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self._status = QLabel("—")
        self._status.setObjectName("StatusLabel")
        root.addSpacing(6)
        root.addWidget(self._status)

        from ..widgets.pending_panel import PendingPanel
        self._pending_panel = PendingPanel(
            "kit_manager", StagingStore(),
            rescan_fn=self.request_rescan.emit
        )
        root.addWidget(self._pending_panel)

        self._selected_pad: Optional[int] = None

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
        self._kits = index.kits
        self._populate_table(self._kits)
        self._status.setText(f"{len(self._kits)} Kits")

    def select_by_path(self, file_path) -> bool:
        """Select the table row whose Kit.file_path matches. Returns True if found."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            kit = item.data(Qt.UserRole) if item else None
            if kit is not None and kit.file_path == file_path:
                self._table.setRowHidden(row, False)
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                return True
        return False

    def _populate_table(self, kits: list[Kit]):
        self._table.setRowCount(0)
        for k in kits:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(k.name)
            name_item.setData(Qt.UserRole, k)
            self._table.setItem(row, 0, name_item)

            self._table.setItem(row, 1, QTableWidgetItem(str(k.pad_count)))

            missing_item = QTableWidgetItem(str(len(k.missing_samples)))
            if k.has_missing_samples:
                missing_item.setForeground(QColor("#E74C3C"))
            else:
                missing_item.setForeground(QColor("#2ECC71"))
            self._table.setItem(row, 2, missing_item)

    def _filter(self):
        text = self._search.text().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            self._table.setRowHidden(row, text != "" and item and text not in item.text().lower())

    def _selected_kit(self) -> Optional[Kit]:
        rows = self._table.selectedItems()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        return item.data(Qt.UserRole) if item else None

    def _on_kit_selected(self):
        kit = self._selected_kit()
        has = kit is not None
        self._rename_btn.setEnabled(has)
        self._dupe_btn.setEnabled(has)
        self._delete_btn.setEnabled(has)
        self._norm_btn.setEnabled(has)
        self._cap_master_btn.setEnabled(has)
        self._cap_pads_btn.setEnabled(has)
        if kit:
            self._current_kit = kit
            self._show_kit_pads(kit)

    def _show_kit_pads(self, kit: Kit):
        self._kit_title.setText(f"🥁  {kit.name}")
        for pad in self._pads:
            pad.set_sample("—", True)
            pad.setObjectName("Card")
            pad.style().unpolish(pad)
            pad.style().polish(pad)

        for i, ref in enumerate(kit.pad_refs[:16]):
            if i < len(self._pads) and ref is not None:
                name = Path(ref.path.replace("\\", "/")).stem
                self._pads[i].set_sample(name, ref.exists)

    def _selected_pad_ref(self):
        if self._selected_pad is None or not self._current_kit:
            return None
        refs = self._current_kit.pad_refs
        if self._selected_pad < len(refs):
            return refs[self._selected_pad]
        return None

    def _on_pad_click(self, pad_index: int):
        self._selected_pad = pad_index
        if not self._current_kit:
            return

        refs = self._current_kit.pad_refs
        ref = refs[pad_index] if pad_index < len(refs) else None
        if ref is not None:
            status = "✅ Vorhanden" if ref.exists else "❌ Fehlt"
            self._pad_info.setText(
                f"Pad {pad_index + 1}\n"
                f"Sample: {ref.path.split('/')[-1]}\n"
                f"Pfad: {ref.path}\n"
                f"Status: {status}"
            )
            exists = bool(ref.abs_path and Path(ref.abs_path).exists())
            suffix = Path(ref.abs_path).suffix if ref.abs_path else ""
            self._listen_btn.setEnabled(pad_preview_enabled(
                exists, suffix, self._player.available, self._player.supports_all_formats,
            ))
            self._show_sample_btn.setEnabled(ref.abs_path is not None)
        else:
            self._pad_info.setText(f"Pad {pad_index + 1}\nKein Sample zugewiesen")
            self._listen_btn.setEnabled(False)
            self._show_sample_btn.setEnabled(False)
            self._player.stop()

        if not self._player.available:
            self._listen_btn.setToolTip("sounddevice nicht installiert — pip install sounddevice")
        elif (
            ref is not None and ref.abs_path
            and not self._player.supports_all_formats
            and Path(ref.abs_path).suffix.lower() != ".wav"
        ):
            self._listen_btn.setToolTip("soundfile nicht installiert — pip install soundfile")
        else:
            self._listen_btn.setToolTip("")
        self._reassign_btn.setEnabled(True)

    def _listen_pad(self):
        ref = self._selected_pad_ref()
        if ref is None or not ref.abs_path:
            return
        self._player.play(Path(ref.abs_path))

    def _show_pad_sample(self):
        ref = self._selected_pad_ref()
        if ref is None or ref.abs_path is None or not self._index:
            self._status.setText("Sample liegt nicht im Index.")
            return
        target = Path(ref.abs_path)
        match = None
        for sample in self._index.samples:
            if sample.file_path == target:
                match = sample
                break
            try:
                if sample.file_path.resolve() == target.resolve():
                    match = sample
                    break
            except OSError:
                continue
        if match is None:
            self._status.setText("Sample liegt nicht im Index.")
            return
        self.open_path.emit("sample_manager", match.file_path)

    def _change_for(self, path: Path):
        if self._staging is None:
            return None
        for change in self._staging.get_all():
            if change.file_path == path:
                return change
        return None

    def _on_folder_dropped(self, folder: str):
        if not self._current_kit or not self._index:
            self._status.setText("Kein Kit ausgewählt.")
            return
        kit = self._current_kit
        existing = self._change_for(kit.file_path)
        if existing is not None and existing.change_type in (ChangeType.RENAME, ChangeType.DELETE):
            self._status.setText(
                "Zuweisung abgebrochen: für dieses Kit liegt schon eine Umbenennung oder Löschung vor."
            )
            return

        from ..core.file_ops import _read_xml, copy_file_to_sd
        from ..core.xml_parser import (
            assign_folder_to_pads, natural_sort_key, map_kit_pads_to_samples,
            _parse_xml_robust_text, validate_xml_text, _first_sample_ref_in,
        )

        if (
            existing is not None
            and existing.change_type == ChangeType.XML_EDIT
            and existing.new_content is not None
        ):
            text = existing.new_content
            enc = existing.encoding or "utf-8"
            source_module = existing.source_module
        else:
            try:
                text, enc = _read_xml(kit.file_path)
            except Exception as e:
                self._status.setText(f"Kit-XML nicht lesbar: {e}")
                return
            source_module = "kit_manager"

        folder_path = Path(folder)
        try:
            audio = [
                path for path in folder_path.iterdir()
                if path.is_file() and path.suffix.lower() in _PAD_AUDIO_EXTENSIONS
            ]
        except OSError as e:
            self._status.setText(f"Ordner nicht lesbar: {e}")
            return
        audio.sort(key=lambda path: natural_sort_key(path.name))
        extra = audio[16:]
        audio = audio[:16]
        if not audio:
            self._status.setText("Keine WAV/AIF-Dateien im Ordner.")
            return

        root = self._index.root_path
        rel_by_path = {}
        outside = []
        for path in audio:
            try:
                rel_by_path[path] = str(path.relative_to(root)).replace("\\", "/")
            except ValueError:
                outside.append(path)

        copied_note = ""
        if outside:
            folder_name = folder_path.name or "Import"
            reply = QMessageBox.question(
                self,
                "Samples kopieren",
                f"Audiodateien jetzt nach SAMPLES/{folder_name}/ kopieren, Kit-XML erst beim Speichern.",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                self._status.setText("Abgebrochen. Nichts kopiert, nichts vorgemerkt.")
                return
            skipped = []
            for path in outside:
                dest = root / "SAMPLES" / folder_name / path.name
                if dest.exists():
                    skipped.append(path.name)
                    continue
                if copy_file_to_sd(path, dest):
                    rel_by_path[path] = str(dest.relative_to(root)).replace("\\", "/")
                else:
                    skipped.append(path.name)
            copied_note = " Kopierte WAVs bleiben liegen, wenn du die Änderung verwirfst."
            if skipped:
                copied_note += " Übersprungen: " + ", ".join(skipped) + "."

        pad_rels = [rel_by_path.get(path) for path in audio]
        while len(pad_rels) < 16:
            pad_rels.append(None)

        parsed = _parse_xml_robust_text(text, context=str(kit.file_path))
        notes = []
        if parsed is not None:
            sounds = parsed.findall(".//sound") or parsed.findall(".//kitRow")
            for index, rel in enumerate(pad_rels):
                if not rel:
                    continue
                if index >= len(sounds):
                    notes.append(f"Pad {index + 1} ohne <sound>")
                    continue
                has_sample = _first_sample_ref_in(sounds[index], root) is not None
                has_osc = sounds[index].find(".//osc1") is not None
                if not has_sample and not has_osc:
                    notes.append(f"Pad {index + 1} ohne <osc1>")

        new_text = assign_folder_to_pads(text, pad_rels)
        if new_text == text:
            detail = (", ".join(notes) + ".") if notes else ""
            self._status.setText(("Keine Pad-Zuweisung möglich. " + detail).strip() + copied_note)
            return
        error = validate_xml_text(new_text, context=str(kit.file_path))
        if error is not None:
            self._status.setText(f"Zuweisung abgebrochen: XML wäre ungültig ({error})." + copied_note)
            return
        if self._staging is None:
            self._status.setText("Kein Zwischenspeicher — nichts vorgemerkt." + copied_note)
            return

        self._staging.add(PendingChange(
            change_type=ChangeType.XML_EDIT,
            file_path=kit.file_path,
            source_module=source_module,
            new_content=new_text,
            encoding=enc,
        ))
        refreshed = _parse_xml_robust_text(new_text, context=str(kit.file_path))
        if refreshed is not None:
            kit.pad_refs = map_kit_pads_to_samples(refreshed, root)
            self._show_kit_pads(kit)
            if self._selected_pad is not None:
                self._on_pad_click(self._selected_pad)
        self._pending_panel.refresh()

        extra_note = " Nur 16 Pads, Rest ignoriert." if extra else ""
        skip_note = (" " + ", ".join(notes) + ".") if notes else ""
        self._status.setText(
            "Vorgemerkt, noch nicht auf der Karte." + extra_note + skip_note + copied_note
        )

    def _reassign_pad(self):
        if self._selected_pad is None or not self._current_kit or not self._index:
            return
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Sample für Pad {self._selected_pad + 1} wählen",
            str(self._index.root_path / "SAMPLES"),
            "Audio Files (*.wav *.aif *.aiff);;All Files (*)"
        )
        if not file_path:
            return

        new_path = Path(file_path)
        try:
            new_rel = str(new_path.relative_to(self._index.root_path)).replace("\\", "/")
        except ValueError:
            QMessageBox.warning(self, "Fehler", "Datei muss auf der SD-Card liegen.")
            return

        kit = self._current_kit
        refs = kit.pad_refs
        if self._selected_pad < len(refs) and refs[self._selected_pad] is not None:
            old_rel = refs[self._selected_pad].path
            from ..core.file_ops import compute_xml_path_update_at, _write_xml

            # Two pads can reference the exact same sample. A plain
            # whole-file replace would repoint every pad using old_rel,
            # not just this one - so find which occurrence (in document
            # order) belongs to *this* pad by counting identical
            # references on earlier pads.
            old_rel_fwd = old_rel.replace("\\", "/")
            occurrence_index = sum(
                1 for r in refs[:self._selected_pad]
                if r is not None and r.path.replace("\\", "/") == old_rel_fwd
            )
            result = compute_xml_path_update_at(kit.file_path, old_rel, new_rel, occurrence_index)
            if result is None:
                self._status.setText("ℹ  Pfad konnte nicht im XML gefunden werden.")
                return
            new_text, enc = result
            if self._staging:
                self._staging.add(PendingChange(
                    change_type=ChangeType.XML_EDIT,
                    file_path=kit.file_path,
                    source_module="kit_manager",
                    new_content=new_text,
                    encoding=enc,
                ))
                self._status.setText(f"⏳  Vorgemerkt: Pad {self._selected_pad + 1} → {new_path.name}")
                self._pending_panel.refresh()
            else:
                try:
                    _write_xml(kit.file_path, new_text, enc)
                    self._status.setText(f"✅  Pad {self._selected_pad + 1} → {new_path.name}")
                    self.request_rescan.emit()
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", str(e))
        else:
            QMessageBox.information(self, "Info", "XML-Schreiben für neue Pads noch nicht implementiert.")

    def _rename_selected(self):
        kit = self._selected_kit()
        if not kit:
            return
        new_name, ok = QInputDialog.getText(self, "Kit umbenennen", "Neuer Name:", text=kit.name)
        if not ok or not new_name.strip():
            return
        new_path = kit.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.RENAME,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_name=f"{new_name.strip()}.XML",
            ))
            self._status.setText(f"⏳  Umbenennen vorgemerkt: {kit.name} → {new_name}")
            self._pending_panel.refresh()
        else:
            try:
                kit.file_path.rename(new_path)
                self._status.setText(f"✅  Umbenannt → {new_name}")
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _duplicate_selected(self):
        kit = self._selected_kit()
        if not kit:
            return
        new_name, ok = QInputDialog.getText(self, "Kit duplizieren", "Name:", text=f"{kit.name}_copy")
        if not ok or not new_name.strip():
            return
        new_path = kit.file_path.parent / f"{new_name.strip()}.XML"
        if new_path.exists():
            QMessageBox.warning(self, "Fehler", "Datei existiert bereits.")
            return
        try:
            shutil.copy2(str(kit.file_path), str(new_path))
            self._status.setText(f"✅  Dupliziert → {new_name}")
            self.request_rescan.emit()
            if self._history:
                from ..core.history import Action
                import shutil as _shutil
                _src, _dst = kit.file_path, new_path
                self._history.push(Action(
                    description=f"Kit dupliziert: {new_name}",
                    undo_fn=lambda p=_dst: p.unlink() if p.exists() else None,
                    redo_fn=lambda s=_src, d=_dst: _shutil.copy2(str(s), str(d)),
                ))
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _delete_selected(self):
        kit = self._selected_kit()
        if not kit:
            return
        reply = QMessageBox.question(
            self, "Löschen",
            f"'{kit.name}' löschen?\n(Erst gespeichert wenn du 'Speichern' drückst)",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.DELETE,
                file_path=kit.file_path,
                source_module="kit_manager",
            ))
            self._status.setText(f"⏳  Zum Löschen vorgemerkt: {kit.name}")
            self._pending_panel.refresh()
        else:
            try:
                kit.file_path.unlink()
                self._status.setText(f"🗑  Gelöscht: {kit.name}")
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _normalize_volumes(self):
        kit = self._selected_kit()
        if not kit or not self._index:
            return

        reply = QMessageBox.question(
            self, "Volumes normalisieren (Audio-Analyse)",
            f"Pad-Volumes in '{kit.name}' per RMS-Analyse angleichen?\n\n"
            "• Jede WAV-Datei wird analysiert\n"
            "• Der lauteste Pad behält sein Volume\n"
            "• Leisere Pads werden proportional angehoben\n"
            "• Pads ohne vorhandenes Sample werden übersprungen",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(kit.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Kit-XML konnte nicht geparst werden.")
            return

        sound_sources = root.find("soundSources")
        if sound_sources is None:
            QMessageBox.warning(self, "Fehler", "Keine <soundSources> in diesem Kit gefunden.")
            return

        pads = []
        for sound in sound_sources.findall("sound"):
            osc1 = sound.find("osc1")
            if osc1 is None:
                continue

            file_name = osc1.get("fileName", "").strip()
            if not file_name:
                fname_elem = osc1.find("fileName")
                if fname_elem is not None:
                    file_name = (fname_elem.text or "").strip()

            if not file_name:
                continue

            rel = file_name.replace("\\", "/").lstrip("/")
            abs_path = self._index.root_path / rel
            if not abs_path.exists():
                continue

            dp = sound.find("defaultParams")
            if dp is None:
                continue

            vol_attr = dp.get("volume", "").strip()
            if vol_attr:
                vol_format = "attr"
                current_vol = vol_attr
            else:
                vol_elem = dp.find("volume")
                if vol_elem is None or not (vol_elem.text or "").strip():
                    continue
                vol_format = "elem"
                current_vol = vol_elem.text.strip()

            pads.append({
                "abs_path": abs_path,
                "current_vol": current_vol,
                "vol_format": vol_format,
                "rms": None,
                "new_vol": None,
            })

        if not pads:
            QMessageBox.information(
                self, "Info",
                "Keine Pads mit vorhandenen Samples und Volume-Werten gefunden."
            )
            return

        try:
            import soundfile as sf
            import numpy as np
        except ImportError:
            QMessageBox.warning(
                self, "Fehlende Bibliothek",
                "soundfile ist nicht installiert.\n\n"
                "Bitte im Terminal ausführen:\n"
                "  pip install soundfile"
            )
            return
        except OSError as e:
            # soundfile IS installed but its native libsndfile library
            # isn't present on this system - raised as OSError at import
            # time, not ImportError, so it needs its own except clause.
            QMessageBox.warning(
                self, "Fehlende Bibliothek",
                f"soundfile ist installiert, aber die native libsndfile-Bibliothek "
                f"fehlt auf diesem System:\n\n{e}"
            )
            return

        for pad in pads:
            try:
                data, _ = sf.read(str(pad["abs_path"]), dtype="float32", always_2d=True)
                mono = np.mean(data, axis=1)
                rms = float(np.sqrt(np.mean(mono ** 2)))
                pad["rms"] = rms if rms > 1e-8 else None
            except Exception as e:
                log.debug("RMS-Berechnung fehlgeschlagen für Pad: %s", e)
                pad["rms"] = None

        valid_pads = [p for p in pads if p["rms"] is not None]
        if not valid_pads:
            QMessageBox.warning(
                self, "Fehler",
                "Konnte keine Sample-Dateien analysieren.\n"
                "Prüfe ob die WAV/AIFF-Dateien lesbar sind."
            )
            return

        target_rms = max(p["rms"] for p in valid_pads)
        for pad in valid_pads:
            gain = target_rms / pad["rms"]
            new_amp = min(vol_to_amp(pad["current_vol"]) * gain, 1.0)
            pad["new_vol"] = amp_to_vol(new_amp)

        import re
        text, enc = _read_xml(kit.file_path)

        sources_match = re.search(r'<soundSources>(.*?)</soundSources>', text, re.DOTALL)
        if not sources_match:
            QMessageBox.warning(self, "Fehler", "<soundSources>-Block nicht im XML gefunden.")
            return

        sources_block = sources_match.group(1)
        replacements = []
        for pad in valid_pads:
            if not (pad["new_vol"] and pad["new_vol"] != pad["current_vol"]):
                continue
            if pad["vol_format"] == "attr":
                replacements.append((f'volume="{pad["current_vol"]}"', f'volume="{pad["new_vol"]}"'))
            else:
                replacements.append((
                    f'<volume>{pad["current_vol"]}</volume>',
                    f'<volume>{pad["new_vol"]}</volume>',
                ))
        sources_block, changed = apply_sequential_replacements(sources_block, replacements)

        if changed == 0:
            self._status.setText("ℹ  Keine Änderungen nötig — alle Pads bereits auf gleicher Lautstärke.")
            return

        start, end = sources_match.start(1), sources_match.end(1)
        new_text = text[:start] + sources_block + text[end:]

        skipped = len(pads) - len(valid_pads)
        skip_note = f" ({skipped} ohne Sample übersprungen)" if skipped else ""
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_content=new_text,
                encoding=enc,
            ))
            self._status.setText(f"⏳  Vorgemerkt: {changed} Pad-Volume(s) normalisiert{skip_note}.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(kit.file_path, new_text, enc)
                self._status.setText(
                    f"✅  {changed} Pad-Volume(s) normalisiert (RMS-Analyse){skip_note}."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _import_kit(self):
        if not self._index:
            QMessageBox.warning(self, "Kein SD-Ordner", "Bitte zuerst einen SD-Card-Ordner laden.")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Kit importieren", "", "XML Files (*.xml *.XML)")
        if not path:
            return
        dest = self._index.root_path / "KITS" / Path(path).name
        if dest.exists():
            reply = QMessageBox.question(self, "Überschreiben?", f"'{dest.name}' existiert. Überschreiben?", QMessageBox.Yes | QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        try:
            shutil.copy2(path, str(dest))
            self._status.setText(f"✅  Importiert: {dest.name}")
            self.request_rescan.emit()
        except Exception as e:
            QMessageBox.warning(self, "Fehler", str(e))

    def _cap_kit_master(self):
        kit = self._selected_kit()
        if not kit:
            return

        threshold, ok = QInputDialog.getInt(
            self, "Kit-Master begrenzen",
            "Maximale Lautstärke für Kit-Master (0 – 50):",
            40, 0, 50, 1
        )
        if not ok:
            return

        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(kit.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Kit-XML konnte nicht geparst werden.")
            return

        dp = root.find("defaultParams")
        if dp is None:
            self._status.setText("ℹ  Kein <defaultParams> im Kit-Root gefunden.")
            return

        vol_str = dp.get("volume", "").strip()
        vol_format = "attr"
        if not vol_str:
            vol_elem = dp.find("volume")
            if vol_elem is not None:
                vol_str = (vol_elem.text or "").strip()
                vol_format = "elem"

        if not vol_str:
            self._status.setText("ℹ  Kein Volume-Wert im Kit-Master gefunden.")
            return

        current_display = vol_to_display(vol_str)
        if current_display <= threshold:
            self._status.setText(
                f"ℹ  Kit-Master liegt bei {current_display:.1f}/50 — kein Cap nötig."
            )
            return

        new_hex = display_to_vol(threshold)
        text, enc = _read_xml(kit.file_path)

        sources_pos = text.find('<soundSources>')
        pre_block  = text[:sources_pos] if sources_pos >= 0 else text
        post_block = text[sources_pos:] if sources_pos >= 0 else ""

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
                file_path=kit.file_path,
                source_module="kit_manager",
                new_content=new_text,
                encoding=enc,
            ))
            self._status.setText(f"⏳  Vorgemerkt: Kit-Master {current_display:.1f}/50 → {threshold}/50.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(kit.file_path, new_text, enc)
                self._status.setText(
                    f"✅  Kit-Master: {current_display:.1f}/50 → {threshold}/50 ({new_hex})."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _cap_pad_volumes(self):
        kit = self._selected_kit()
        if not kit:
            return

        threshold, ok = QInputDialog.getInt(
            self, "Pad-Volumes begrenzen",
            "Maximale Lautstärke pro Pad (0 – 50):",
            40, 0, 50, 1
        )
        if not ok:
            return

        import re
        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml, _write_xml

        root = _parse_xml_robust(kit.file_path)
        if root is None:
            QMessageBox.warning(self, "Fehler", "Kit-XML konnte nicht geparst werden.")
            return

        sound_sources = root.find("soundSources")
        if sound_sources is None:
            self._status.setText("ℹ  Keine <soundSources> in diesem Kit gefunden.")
            return

        caps = []
        for sound in sound_sources.findall("sound"):
            dp = sound.find("defaultParams")
            if dp is None:
                continue
            vol_str = dp.get("volume", "").strip()
            vol_format = "attr"
            if not vol_str:
                vol_elem = dp.find("volume")
                if vol_elem is not None:
                    vol_str = (vol_elem.text or "").strip()
                    vol_format = "elem"
            if vol_str and vol_to_display(vol_str) > threshold:
                caps.append((vol_str, display_to_vol(threshold), vol_format))

        if not caps:
            self._status.setText(
                f"ℹ  Alle Pad-Volumes bereits ≤ {threshold}/50 — kein Cap nötig."
            )
            return

        text, enc = _read_xml(kit.file_path)

        sources_match = re.search(r'<soundSources>(.*?)</soundSources>', text, re.DOTALL)
        if not sources_match:
            QMessageBox.warning(self, "Fehler", "<soundSources>-Block nicht gefunden.")
            return

        sources_block = sources_match.group(1)
        replacements = []
        for current_hex, new_hex, fmt in caps:
            if fmt == "attr":
                replacements.append((f'volume="{current_hex}"', f'volume="{new_hex}"'))
            else:
                replacements.append((f'<volume>{current_hex}</volume>', f'<volume>{new_hex}</volume>'))
        sources_block, changed = apply_sequential_replacements(sources_block, replacements)

        if changed == 0:
            self._status.setText("ℹ  Keine Änderungen vorgenommen.")
            return

        start, end = sources_match.start(1), sources_match.end(1)
        new_text = text[:start] + sources_block + text[end:]
        if self._staging:
            self._staging.add(PendingChange(
                change_type=ChangeType.XML_EDIT,
                file_path=kit.file_path,
                source_module="kit_manager",
                new_content=new_text,
                encoding=enc,
                   ))
            self._status.setText(f"⏳  Vorgemerkt: {changed} Pad-Volume(s) auf max. {threshold}/50.")
            self._pending_panel.refresh()
        else:
            try:
                _write_xml(kit.file_path, new_text, enc)
                self._status.setText(
                    f"✅  {changed} Pad-Volume(s) auf max. {threshold}/50 begrenzt."
                )
                self.request_rescan.emit()
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

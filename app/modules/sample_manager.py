"""
DelugeHub — Sample Manager Module
Browse, move, rename, delete samples. Audio preview. Usage analysis.
"""
import wave
import struct
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QFrame, QAbstractItemView,
    QFileDialog, QInputDialog, QMessageBox, QLineEdit,
    QProgressBar, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QLinearGradient, QBrush

from ..core.models import SDCardIndex, Sample
from ..core.file_ops import rename_sample, move_sample, delete_sample, copy_file_to_sd

AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".mp3", ".flac", ".ogg"}


# ── Waveform widget (pure QPainter, no external libs) ─────────────────────
class WaveformWidget(QWidget):
    def __init__(self):
        super().__init__()
        self._samples: list[float] = []
        self.setMinimumHeight(64)
        self.setMaximumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # Max number of raw frames to read for waveform display.
    # 88 200 frames @ 44.1 kHz = 2 seconds, good enough for a full overview
    # of most samples without reading huge files entirely into memory.
    _MAX_FRAMES = 88_200

    def load_wav(self, path: Path):
        """
        Read a WAV file and build a ~200-point downsampled amplitude envelope
        that spans the WHOLE file (not just the first 93 ms).
        For files longer than _MAX_FRAMES we spread reads evenly across the
        file so the shape is still representative.
        """
        try:
            with wave.open(str(path), "rb") as wf:
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()

                if n_frames == 0:
                    self._samples = []
                    self.update()
                    return

                # Read up to _MAX_FRAMES evenly spaced across the file.
                if n_frames <= self._MAX_FRAMES:
                    frames = wf.readframes(n_frames)
                else:
                    # Read _MAX_FRAMES frames starting at a stride-sampled
                    # position so we cover the full file.
                    stride = n_frames // self._MAX_FRAMES
                    chunks: list[bytes] = []
                    for i in range(self._MAX_FRAMES):
                        wf.setpos(i * stride)
                        chunks.append(wf.readframes(1))
                    frames = b"".join(chunks)

            bytes_per_sample = sampwidth * n_channels

            if sampwidth == 2:
                count = len(frames) // 2
                raw = struct.unpack(f"<{count}h", frames[:count * 2])
                normalized = [s / 32768.0 for s in raw]
            elif sampwidth == 1:
                raw = struct.unpack(f"{len(frames)}B", frames)
                normalized = [(s - 128) / 128.0 for s in raw]
            else:
                normalized = []

            if n_channels > 1:
                # Mix down to mono by averaging channels.
                normalized = [
                    sum(normalized[i:i + n_channels]) / n_channels
                    for i in range(0, len(normalized) - n_channels + 1, n_channels)
                ]

            # Downsample to ~200 display points using peak amplitude per chunk.
            target = 200
            chunk = max(1, len(normalized) // target)
            self._samples = [
                max(abs(s) for s in normalized[i:i + chunk])
                for i in range(0, len(normalized), chunk)
            ][:target]

        except Exception:
            self._samples = []
        self.update()

    def clear(self):
        self._samples = []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        mid = h // 2

        # Background: subtle top-to-bottom gradient
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0.0, QColor("#0A1F3C"))
        bg_grad.setColorAt(0.5, QColor("#0F3460"))
        bg_grad.setColorAt(1.0, QColor("#0A1F3C"))
        painter.fillRect(0, 0, w, h, QBrush(bg_grad))

        if not self._samples:
            painter.setPen(QPen(QColor("#1A3A6E"), 1))
            painter.drawLine(0, mid, w, mid)
            painter.end()
            return

        # Waveform gradient: dark at edges, bright blue in the center
        wave_grad = QLinearGradient(0, 0, 0, h)
        wave_grad.setColorAt(0.0,  QColor("#0F3460"))   # top — dark blue
        wave_grad.setColorAt(0.3,  QColor("#1E6FBB"))   # upper third
        wave_grad.setColorAt(0.5,  QColor("#5BB8FF"))   # center — bright
        wave_grad.setColorAt(0.7,  QColor("#1E6FBB"))   # lower third
        wave_grad.setColorAt(1.0,  QColor("#0F3460"))   # bottom — dark blue

        pen = QPen(QBrush(wave_grad), 1.5)
        painter.setPen(pen)

        n = len(self._samples)
        step = w / max(n, 1)

        for i, val in enumerate(self._samples):
            x = int(i * step)
            amp = int(val * (mid - 4))
            # Draw symmetrically from centre outward (mirrored waveform)
            painter.drawLine(x, mid - amp, x, mid + amp)

        # Subtle centre line
        painter.setPen(QPen(QColor(91, 184, 255, 50), 1))
        painter.drawLine(0, mid, w, mid)

        painter.end()


# ── Audio player (optional sounddevice) ───────────────────────────────────
class AudioPlayer:
    def __init__(self):
        self._playing = False
        try:
            import sounddevice as sd
            import numpy as np
            self._sd = sd
            self._np = np
            self._available = True
        except ImportError:
            self._available = False

    def play(self, path: Path):
        if not self._available:
            return
        self.stop()
        try:
            with wave.open(str(path), "rb") as wf:
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                sample_rate = wf.getframerate()
                frames = wf.readframes(n_frames)

            if sampwidth == 2:
                data = self._np.frombuffer(frames, dtype=self._np.int16).astype(float) / 32768.0
            elif sampwidth == 1:
                data = (self._np.frombuffer(frames, dtype=self._np.uint8).astype(float) - 128) / 128.0
            else:
                return

            if n_channels > 1:
                data = data.reshape(-1, n_channels)

            self._playing = True
            self._sd.play(data, sample_rate)
        except Exception:
            pass

    def stop(self):
        if self._available:
            try:
                self._sd.stop()
            except Exception:
                pass
        self._playing = False

    @property
    def available(self):
        return self._available


# ── Sample Manager ─────────────────────────────────────────────────────────
class SampleManagerModule(QWidget):
    request_rescan = Signal()

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._player = AudioPlayer()
        self._current_sample: Optional[Sample] = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 16)
        root.setSpacing(0)

        # Header
        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(self._lbl("📁  Sample Manager", "PageTitle"))
        title_col.addWidget(self._lbl("Samples organisieren, umbenennen, verschieben, Duplikate & ungenutzte finden", "PageSubtitle"))
        hdr.addLayout(title_col)
        hdr.addStretch()

        self._import_btn = QPushButton("⬇  Importieren")
        self._import_btn.setToolTip("Samples von außerhalb auf die SD-Card importieren")
        self._import_btn.clicked.connect(self._batch_import)
        self._import_btn.setFixedHeight(36)

        self._unused_btn = QPushButton("🗑  Ungenutzte finden")
        self._unused_btn.setObjectName("SecondaryButton")
        self._unused_btn.clicked.connect(self._show_unused)
        self._unused_btn.setFixedHeight(36)

        self._dupes_btn = QPushButton("🔁  Duplikate")
        self._dupes_btn.setObjectName("SecondaryButton")
        self._dupes_btn.clicked.connect(self._find_duplicates)
        self._dupes_btn.setFixedHeight(36)

        hdr.addWidget(self._import_btn)
        hdr.addWidget(self._unused_btn)
        hdr.addWidget(self._dupes_btn)
        root.addLayout(hdr)
        root.addSpacing(14)

        # Search bar
        search_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Samples suchen…")
        self._search.textChanged.connect(self._filter_table)
        search_row.addWidget(QLabel("🔎"))
        search_row.addWidget(self._search)
        root.addLayout(search_row)
        root.addSpacing(8)

        # Main splitter: tree | table | detail
        splitter = QSplitter(Qt.Horizontal)

        # Folder tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabel("Ordner")
        self._tree.setMinimumWidth(180)
        self._tree.setMaximumWidth(260)
        self._tree.itemClicked.connect(self._on_folder_click)
        splitter.addWidget(self._tree)

        # Sample table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Name", "Pfad", "Größe", "Genutzt von", "Format"])
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Interactive)
        hv.setSectionResizeMode(1, QHeaderView.Stretch)
        hv.setSectionResizeMode(2, QHeaderView.Fixed)
        hv.setSectionResizeMode(3, QHeaderView.Fixed)
        hv.setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 200)
        self._table.setColumnWidth(2, 70)
        self._table.setColumnWidth(3, 80)
        self._table.setColumnWidth(4, 60)
        self._table.currentItemChanged.connect(self._on_table_selection)
        self._table.doubleClicked.connect(self._play_selected)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        splitter.addWidget(self._table)

        # Detail panel
        detail = QFrame()
        detail.setObjectName("Card")
        detail.setMinimumWidth(200)
        detail.setMaximumWidth(260)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(12, 12, 12, 12)
        detail_layout.setSpacing(8)

        self._detail_name = QLabel("—")
        self._detail_name.setWordWrap(True)
        self._detail_name.setObjectName("SynthTitle")

        self._waveform = WaveformWidget()

        self._play_btn = QPushButton("▶  Abspielen")
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self._play_selected)

        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setObjectName("SecondaryButton")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._player.stop)

        if not self._player.available:
            self._play_btn.setToolTip("sounddevice nicht installiert — pip install sounddevice numpy")

        detail_layout.addWidget(QLabel("Vorschau"))
        detail_layout.addWidget(self._waveform)
        pb_row = QHBoxLayout()
        pb_row.addWidget(self._play_btn)
        pb_row.addWidget(self._stop_btn)
        detail_layout.addLayout(pb_row)
        detail_layout.addSpacing(8)

        detail_layout.addWidget(self._lbl("Details", "SectionTitle"))
        self._detail_info = QLabel("—")
        self._detail_info.setWordWrap(True)
        self._detail_info.setObjectName("PageSubtitle")
        detail_layout.addWidget(self._detail_name)
        detail_layout.addWidget(self._detail_info)

        detail_layout.addSpacing(8)
        detail_layout.addWidget(self._lbl("Genutzt in", "SectionTitle"))
        self._usage_list = QTreeWidget()
        self._usage_list.setHeaderHidden(True)
        self._usage_list.setMaximumHeight(140)
        detail_layout.addWidget(self._usage_list)

        # Actions
        detail_layout.addSpacing(4)
        detail_layout.addWidget(self._lbl("Aktionen", "SectionTitle"))

        self._rename_btn = QPushButton("✏  Umbenennen")
        self._rename_btn.setEnabled(False)
        self._rename_btn.clicked.connect(self._rename_selected)

        self._move_btn = QPushButton("📂  Verschieben")
        self._move_btn.setObjectName("SecondaryButton")
        self._move_btn.setEnabled(False)
        self._move_btn.clicked.connect(self._move_selected)

        self._delete_btn = QPushButton("🗑  Löschen")
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._delete_selected)

        detail_layout.addWidget(self._rename_btn)
        detail_layout.addWidget(self._move_btn)
        detail_layout.addWidget(self._delete_btn)
        detail_layout.addStretch()

        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        root.addWidget(splitter, 1)

        # Status
        self._status = QLabel("Kein Index geladen.")
        self._status.setObjectName("StatusLabel")
        root.addSpacing(6)
        root.addWidget(self._status)

    def _lbl(self, text, obj=""):
        l = QLabel(text)
        if obj:
            l.setObjectName(obj)
        return l

    # ── Public API ─────────────────────────────────────────────────────────
    def update_index(self, index: SDCardIndex):
        self._index = index
        self._populate_tree()
        self._populate_table(index.samples)
        self._status.setText(
            f"{len(index.samples)} Samples  •  "
            f"{index.total_sample_size_mb:.1f} MB  •  "
            f"{len(index.unused_samples)} ungenutzt"
        )

    # ── Tree ───────────────────────────────────────────────────────────────
    def _populate_tree(self):
        self._tree.clear()
        if not self._index:
            return

        root_item = QTreeWidgetItem(["📁 SAMPLES (alle)"])
        root_item.setData(0, Qt.UserRole, None)
        self._tree.addTopLevelItem(root_item)

        folders: dict[str, QTreeWidgetItem] = {}
        for s in self._index.samples:
            try:
                rel = str(s.file_path.relative_to(self._index.root_path)).replace("\\", "/")
                parts = rel.split("/")
                if len(parts) > 1:
                    folder_path = "/".join(parts[:-1])
                    if folder_path not in folders:
                        # Build tree path
                        parent = root_item
                        built = ""
                        for part in parts[:-1]:
                            built = (built + "/" + part).lstrip("/")
                            if built not in folders:
                                item = QTreeWidgetItem([f"📁 {part}"])
                                item.setData(0, Qt.UserRole, built)
                                parent.addChild(item)
                                folders[built] = item
                            parent = folders[built]
            except ValueError:
                pass

        root_item.setExpanded(True)

    def _on_folder_click(self, item: QTreeWidgetItem):
        folder = item.data(0, Qt.UserRole)
        if folder is None:
            self._populate_table(self._index.samples if self._index else [])
        else:
            filtered = [
                s for s in (self._index.samples if self._index else [])
                if folder.lower() in str(s.file_path).replace("\\", "/").lower()
            ]
            self._populate_table(filtered)

    # ── Table ──────────────────────────────────────────────────────────────
    def _populate_table(self, samples: list[Sample]):
        self._table.setRowCount(0)
        for s in samples:
            row = self._table.rowCount()
            self._table.insertRow(row)

            name_item = QTableWidgetItem(s.name)
            name_item.setData(Qt.UserRole, s)
            self._table.setItem(row, 0, name_item)

            try:
                rel = str(s.file_path.relative_to(self._index.root_path)).replace("\\", "/")
            except (ValueError, AttributeError):
                rel = str(s.file_path)
            self._table.setItem(row, 1, QTableWidgetItem(rel))

            size_str = f"{s.size_kb:.0f} KB" if s.size_kb < 1024 else f"{s.size_mb:.1f} MB"
            self._table.setItem(row, 2, QTableWidgetItem(size_str))

            usage = str(len(s.referenced_by))
            u_item = QTableWidgetItem(usage)
            if not s.is_used:
                u_item.setForeground(QColor("#E67E22"))
            self._table.setItem(row, 3, u_item)

            ext = s.file_path.suffix.upper().lstrip(".")
            self._table.setItem(row, 4, QTableWidgetItem(ext))

        self._filter_table()

    def _filter_table(self):
        text = self._search.text().lower()
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            path_item = self._table.item(row, 1)
            visible = (not text or
                       (item and text in item.text().lower()) or
                       (path_item and text in path_item.text().lower()))
            self._table.setRowHidden(row, not visible)

    def _on_table_selection(self, current, previous):
        if not current:
            return
        row = current.row()
        item = self._table.item(row, 0)
        if not item:
            return
        sample: Sample = item.data(Qt.UserRole)
        if not sample:
            return
        self._current_sample = sample
        self._show_detail(sample)

    def _show_detail(self, s: Sample):
        self._detail_name.setText(s.name)
        size_str = f"{s.size_kb:.0f} KB" if s.size_kb < 1024 else f"{s.size_mb:.2f} MB"
        info = f"Größe: {size_str}\n"
        if s.sample_rate:
            info += f"Sample Rate: {s.sample_rate} Hz\n"
        if s.channels:
            info += f"Kanäle: {s.channels}\n"
        if s.bit_depth:
            info += f"Bit-Tiefe: {s.bit_depth} bit\n"
        info += f"Genutzt von: {len(s.referenced_by)} Dateien"
        self._detail_info.setText(info)

        # Waveform
        if s.file_path.suffix.lower() == ".wav" and s.file_path.exists():
            self._waveform.load_wav(s.file_path)
        else:
            self._waveform.clear()

        # Usage tree
        self._usage_list.clear()
        for ref_path in s.referenced_by[:20]:
            item = QTreeWidgetItem([ref_path.name])
            item.setToolTip(0, str(ref_path))
            self._usage_list.addTopLevelItem(item)
        if len(s.referenced_by) > 20:
            QTreeWidgetItem(self._usage_list, [f"… +{len(s.referenced_by)-20} weitere"])

        if not s.is_used:
            unused_lbl = QTreeWidgetItem(self._usage_list, ["⚠ Ungenutzt"])
            unused_lbl.setForeground(0, QColor("#E67E22"))

        # Enable actions
        can_edit = s.file_path.exists()
        self._rename_btn.setEnabled(can_edit)
        self._move_btn.setEnabled(can_edit)
        self._delete_btn.setEnabled(can_edit)
        self._play_btn.setEnabled(
            can_edit and s.file_path.suffix.lower() == ".wav"
            and self._player.available
        )
        self._stop_btn.setEnabled(True)

    def _play_selected(self):
        if self._current_sample and self._player.available:
            self._player.play(self._current_sample.file_path)

    # ── File operations ────────────────────────────────────────────────────
    def _rename_selected(self):
        if not self._current_sample or not self._index:
            return
        s = self._current_sample
        new_name, ok = QInputDialog.getText(
            self, "Umbenennen", f"Neuer Name für '{s.name}':",
            text=s.name
        )
        if not ok or not new_name.strip() or new_name == s.name:
            return

        new_abs, updated = rename_sample(s.file_path, new_name.strip(), self._index.root_path)
        if new_abs:
            self._status.setText(f"✅  Umbenannt → {new_name}  |  {len(updated)} XMLs aktualisiert")
            self.request_rescan.emit()
        else:
            QMessageBox.warning(self, "Fehler", f"Umbenennen fehlgeschlagen.")

    def _move_selected(self):
        if not self._current_sample or not self._index:
            return
        s = self._current_sample
        folder = QFileDialog.getExistingDirectory(
            self, "Zielordner wählen",
            str(self._index.root_path / "SAMPLES")
        )
        if not folder:
            return

        new_abs, updated = move_sample(s.file_path, Path(folder), self._index.root_path)
        if new_abs:
            self._status.setText(f"✅  Verschoben nach {Path(folder).name}  |  {len(updated)} XMLs aktualisiert")
            self.request_rescan.emit()
        else:
            QMessageBox.warning(self, "Fehler", "Verschieben fehlgeschlagen.")

    def _delete_selected(self):
        if not self._current_sample:
            return
        s = self._current_sample
        if s.is_used:
            reply = QMessageBox.warning(
                self, "Sample in Verwendung",
                f"'{s.name}' wird von {len(s.referenced_by)} Datei(en) verwendet!\n"
                "Trotzdem löschen?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        else:
            reply = QMessageBox.question(
                self, "Löschen bestätigen",
                f"'{s.name}' wirklich löschen?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        if delete_sample(s.file_path):
            self._status.setText(f"🗑  Gelöscht: {s.name}")
            self.request_rescan.emit()
        else:
            QMessageBox.warning(self, "Fehler", "Löschen fehlgeschlagen.")

    # ── Batch import ───────────────────────────────────────────────────────
    def _batch_import(self):
        if not self._index:
            QMessageBox.information(self, "Info", "Bitte zuerst eine SD-Card scannen.")
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "Samples importieren", "",
            "Audio Files (*.wav *.aif *.aiff *.mp3 *.flac *.ogg);;All Files (*)"
        )
        if not files:
            return

        target = QFileDialog.getExistingDirectory(
            self, "Zielordner auf SD-Card",
            str(self._index.root_path / "SAMPLES")
        )
        if not target:
            return

        success = 0
        for f in files:
            src = Path(f)
            dest = Path(target) / src.name
            if copy_file_to_sd(src, dest):
                success += 1

        self._status.setText(f"✅  {success}/{len(files)} Samples importiert.")
        if success > 0:
            self.request_rescan.emit()

    # ── Unused & duplicates ────────────────────────────────────────────────
    def _show_unused(self):
        if not self._index:
            return
        unused = self._index.unused_samples
        self._populate_table(unused)
        self._status.setText(f"{len(unused)} ungenutzte Samples angezeigt. Vorsicht beim Löschen!")

    def _find_duplicates(self):
        if not self._index:
            return
        # Find by name
        seen: dict[str, list[Sample]] = {}
        for s in self._index.samples:
            key = s.name.lower()
            if key not in seen:
                seen[key] = []
            seen[key].append(s)
        dupes = [s for samples in seen.values() if len(samples) > 1 for s in samples]
        self._populate_table(dupes)
        self._status.setText(f"{len(dupes)} potenzielle Duplikate (gleicher Dateiname).")

    # ── Context menu ───────────────────────────────────────────────────────
    def _context_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        item = self._table.item(row, 0)
        if not item:
            return
        s: Sample = item.data(Qt.UserRole)

        menu = QMenu(self)
        if s.file_path.suffix.lower() == ".wav" and s.file_path.exists():
            act_play = menu.addAction("▶  Abspielen")
            act_play.triggered.connect(lambda: self._player.play(s.file_path))
        menu.addSeparator()
        act_rename = menu.addAction("✏  Umbenennen")
        act_rename.triggered.connect(self._rename_selected)
        act_move = menu.addAction("📂  Verschieben")
        act_move.triggered.connect(self._move_selected)
        menu.addSeparator()
        act_del = menu.addAction("🗑  Löschen")
        act_del.triggered.connect(self._delete_selected)
        act_copy = menu.addAction("📋  Pfad kopieren")
        act_copy.triggered.connect(lambda: __import__("PySide6.QtWidgets", fromlist=["QApplication"]).QApplication.clipboard().setText(str(s.file_path)))
        menu.exec(self._table.viewport().mapToGlobal(pos))

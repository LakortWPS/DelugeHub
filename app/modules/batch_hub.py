"""
DelugeHub — Batch Hub Module
Cross-module batch operations: rename, export, delete, normalize, tag.
"""
import logging
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
    QScrollArea, QGroupBox, QTabWidget, QSpinBox,
    QDialog, QDialogButtonBox, QListWidget
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from ..core.models import SDCardIndex
from ..core.staging import StagingStore, PendingChange, ChangeType
from ..core.volume_utils import (
    vol_to_display as _vol_to_display, display_to_vol as _display_to_vol,
    apply_sequential_replacements,
)

log = logging.getLogger(__name__)

# ── Rename-Schema Schemas ──────────────────────────────────────────────────
RENAME_SCHEMAS = [
    ("Deluge-Style  (A001, A002 … B001 …)", "deluge"),
    ("Kompakt       (A1, A2 … B1 …)",       "compact"),
    ("Freies Pattern  ({name}, {index} …)", "pattern"),
    ("Prefix + Nummer  (PREFIX001 …)",       "prefix_num"),
    ("Name + Affix   (PREFIX_{name}_SUFFIX)", "name_affix"),
]


def _compute_rename(schema: str, extra: str, name: str, abs_index: int) -> str:
    """Berechnet den neuen Dateinamen (ohne Extension).

    abs_index: 0-basierter Index (start_index bereits eingerechnet).
    """
    if schema in ("deluge", "compact"):
        # Deluge nutzt A1–A9, B1–B9, … Z1–Z9 = 234 Slots.
        # Darüber hinaus: doppelte Buchstaben AA1, AB1, … (wie Excel-Spalten).
        bucket = abs_index // 9
        num    = (abs_index % 9) + 1
        if bucket < 26:
            letter = chr(ord("A") + bucket)
        else:
            # Excel-Stil: AA, AB, … AZ, BA, …
            hi = (bucket - 26) // 26
            lo = (bucket - 26) % 26
            letter = chr(ord("A") + hi) + chr(ord("A") + lo)
        if schema == "deluge":
            return f"{letter}{num:03d}"
        return f"{letter}{num}"
    elif schema == "pattern":
        res = extra if extra.strip() else "{name}"
        res = res.replace("{name}", name)
        res = res.replace("{index}", str(abs_index + 1).zfill(3))
        res = res.replace("{INDEX}", str(abs_index + 1))
        return res
    elif schema == "prefix_num":
        prefix = extra.strip() or "FILE"
        return f"{prefix}{str(abs_index + 1).zfill(3)}"
    elif schema == "name_affix":
        sep = "|||"
        if sep in extra:
            pfx, sfx = extra.split(sep, 1)
        else:
            pfx, sfx = extra, ""
        return f"{pfx}{name}{sfx}"
    return name


class SimpleWorker(QThread):
    """Lightweight worker for single-function background tasks (export, delete)."""
    progress = Signal(int)
    finished = Signal(str)   # status message
    error = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            msg = self._fn(self.progress.emit, *self._args, **self._kwargs)
            self.finished.emit(msg or "")
        except Exception as e:
            log.error("SimpleWorker fehlgeschlagen: %s", e)
            self.error.emit(str(e))


class BatchWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict, list)   # (stats, list[PendingChange])
    error = Signal(str)

    def __init__(self, items: list, operation: str, params: dict):
        super().__init__()
        self.items = items
        self.operation = operation
        self.params = params

    def run(self):
        try:
            stats, pending = self._process()
            self.finished.emit(stats, pending)
        except Exception as e:
            self.error.emit(str(e))

    def _process(self) -> tuple[dict, list]:
        op = self.operation
        total = len(self.items)
        success = failed = 0
        pending: list[PendingChange] = []

        for i, item in enumerate(self.items):
            pct = int((i + 1) / max(total, 1) * 100)
            self.progress.emit(pct, f"[{i+1}/{total}] {item.file_path.name}")

            try:
                if op == "rename":
                    change = self._do_rename(item, i)
                    if change:
                        pending.append(change)
                elif op == "delete":
                    pending.append(PendingChange(
                        change_type=ChangeType.DELETE,
                        file_path=item.file_path,
                        source_module="batch_hub",
                    ))
                elif op == "export":
                    self._do_export(item)   # direkt — kein Staging nötig
                elif op == "normalize_volume":
                    change = self._do_normalize(item)
                    if change:
                        pending.append(change)
                elif op == "cap_kit_master":
                    change = self._do_cap_kit_master(item)
                    if change:
                        pending.append(change)
                elif op == "cap_pad_volumes":
                    change = self._do_cap_pad_volumes(item)
                    if change:
                        pending.append(change)
                elif op == "cap_clip_volumes":
                    change = self._do_cap_clip_volumes(item)
                    if change:
                        pending.append(change)
                success += 1
            except Exception as e:
                log.warning("Batch-Op fehlgeschlagen für %s: %s", item.file_path.name, e)
                failed += 1

        return {"success": success, "failed": failed, "total": total}, pending

    def _do_rename(self, item, index: int) -> Optional[PendingChange]:
        schema: str = self.params.get("schema", "pattern")
        extra: str  = self.params.get("extra", "{name}")
        start: int  = self.params.get("start_index", 1)
        abs_index   = (start - 1) + index

        stem = _compute_rename(schema, extra, item.name, abs_index)
        new_name = stem if stem.lower().endswith(".xml") else stem + ".XML"
        new_path = item.file_path.parent / new_name
        if not new_path.exists() and new_name != item.file_path.name:
            return PendingChange(
                change_type=ChangeType.RENAME,
                file_path=item.file_path,
                source_module="batch_hub",
                new_name=new_name,
            )
        return None

    def _do_export(self, item):
        dest_dir = Path(self.params.get("dest_dir", "."))
        shutil.copy2(str(item.file_path), str(dest_dir / item.file_path.name))

    def _do_normalize(self, item) -> Optional[PendingChange]:
        """Setzt alle Pad-Volumes (nur innerhalb <soundSources>) auf Maximum."""
        from ..core.file_ops import _read_xml
        text, enc = _read_xml(item.file_path)

        sources_match = re.search(r'<soundSources>(.*?)</soundSources>', text, re.DOTALL)
        if not sources_match:
            return None

        block = sources_match.group(1)
        block = re.sub(r'(<volume>)\s*0x[0-9A-Fa-f]+\s*(</volume>)', r'\g<1>0x7FFFFFFF\2', block)
        block = re.sub(r'(volume=")0x[0-9A-Fa-f]+(")', r'\g<1>0x7FFFFFFF\2', block)

        s, e = sources_match.start(1), sources_match.end(1)
        new_text = text[:s] + block + text[e:]
        if new_text == text:
            return None
        return PendingChange(
            change_type=ChangeType.XML_EDIT,
            file_path=item.file_path,
            source_module="batch_hub",
            new_content=new_text,
            encoding=enc,
        )

    def _do_cap_kit_master(self, item) -> Optional[PendingChange]:
        """Begrenzt Kit-Master-Volume auf params['threshold']."""
        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml
        threshold = self.params.get("threshold", 40)

        root = _parse_xml_robust(item.file_path)
        if root is None:
            return None
        dp = root.find("defaultParams")
        if dp is None:
            return None

        vol_str = dp.get("volume", "").strip()
        vol_format = "attr"
        if not vol_str:
            vol_elem = dp.find("volume")
            if vol_elem is not None:
                vol_str = (vol_elem.text or "").strip()
                vol_format = "elem"
        if not vol_str or _vol_to_display(vol_str) <= threshold:
            return None

        new_hex = _display_to_vol(threshold)
        text, enc = _read_xml(item.file_path)

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
            return None
        return PendingChange(
            change_type=ChangeType.XML_EDIT,
            file_path=item.file_path,
            source_module="batch_hub",
            new_content=new_pre + post_block,
            encoding=enc,
        )

    def _do_cap_pad_volumes(self, item) -> Optional[PendingChange]:
        """Begrenzt alle Pad-Volumes im Kit auf params['threshold']."""
        from ..core.xml_parser import _parse_xml_robust
        from ..core.file_ops import _read_xml
        threshold = self.params.get("threshold", 40)

        root = _parse_xml_robust(item.file_path)
        if root is None:
            return None
        sound_sources = root.find("soundSources")
        if sound_sources is None:
            return None

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
            if vol_str and _vol_to_display(vol_str) > threshold:
                caps.append((vol_str, _display_to_vol(threshold), vol_format))

        if not caps:
            return None

        text, enc = _read_xml(item.file_path)
        sources_match = re.search(r'<soundSources>(.*?)</soundSources>', text, re.DOTALL)
        if not sources_match:
            return None

        block = sources_match.group(1)
        replacements = []
        for current_hex, new_hex, fmt in caps:
            if fmt == "attr":
                replacements.append((f'volume="{current_hex}"', f'volume="{new_hex}"'))
            else:
                replacements.append((f'<volume>{current_hex}</volume>', f'<volume>{new_hex}</volume>'))
        block, _changed = apply_sequential_replacements(block, replacements)

        s, e = sources_match.start(1), sources_match.end(1)
        new_text = text[:s] + block + text[e:]
        if new_text == text:
            return None
        return PendingChange(
            change_type=ChangeType.XML_EDIT,
            file_path=item.file_path,
            source_module="batch_hub",
            new_content=new_text,
            encoding=enc,
        )

    def _do_cap_clip_volumes(self, item) -> Optional[PendingChange]:
        """Begrenzt alle Clip-Volumes (kitParams/synthParams) im Song auf params['threshold']."""
        from ..core.file_ops import _read_xml
        threshold = self.params.get("threshold", 40)

        text, enc = _read_xml(item.file_path)

        def cap_vol(m):
            if _vol_to_display(m.group(2)) > threshold:
                return m.group(1) + f'volume="{_display_to_vol(threshold)}"'
            return m.group(0)

        new_text = re.sub(
            r'(<(?:kitParams|synthParams)\b[^>]*)volume="(0x[0-9A-Fa-f]+)"',
            cap_vol,
            text,
        )
        if new_text == text:
            return None
        return PendingChange(
            change_type=ChangeType.XML_EDIT,
            file_path=item.file_path,
            source_module="batch_hub",
            new_content=new_text,
            encoding=enc,
        )


class BatchHubModule(QWidget):
    request_rescan = Signal()

    def __init__(self):
        super().__init__()
        self._index: Optional[SDCardIndex] = None
        self._worker = None
        self._staging: Optional[StagingStore] = None
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

        tabs = QTabWidget()
        tabs.addTab(self._build_content_tab("songs"), "🎵 Songs")
        tabs.addTab(self._build_content_tab("kits"), "🥁 Kits")
        tabs.addTab(self._build_content_tab("synths"), "🎹 Synths")
        tabs.addTab(self._build_sample_tab(), "📁 Samples")
        tabs.addTab(self._build_xml_tab(), "🔧 XML Tools")
        root.addWidget(tabs, 1)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setVisible(False)

        self._status = QLabel("Bereit.")
        self._status.setObjectName("StatusLabel")

        root.addSpacing(8)
        root.addWidget(self._progress)
        root.addWidget(self._status)

        from ..widgets.pending_panel import PendingPanel
        self._pending_panel = PendingPanel(
            "batch_hub", StagingStore(),
            rescan_fn=self.request_rescan.emit
        )
        root.addWidget(self._pending_panel)

    def _build_content_tab(self, content_type: str) -> QWidget:
        widget = QWidget()
        widget.setProperty("content_type", content_type)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

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
        if content_type == "kits":
            op_combo.addItem("Kit-Master begrenzen")
            op_combo.addItem("Pad-Volumes begrenzen")
        if content_type == "songs":
            op_combo.addItem("Clip-Volumes begrenzen")

        op_row.addWidget(op_lbl)
        op_row.addWidget(op_combo)
        op_row.addStretch()
        ops_layout.addLayout(op_row)

        # ── Rename-Controls (nur bei "Batch Umbenennen" sichtbar) ──────────
        rename_frame = QFrame()
        rename_layout = QVBoxLayout(rename_frame)
        rename_layout.setContentsMargins(0, 4, 0, 0)
        rename_layout.setSpacing(6)

        # Zeile 1: Schema-Dropdown + Startindex
        schema_row = QHBoxLayout()
        schema_lbl = QLabel("Schema:")
        schema_lbl.setFixedWidth(100)
        schema_combo = QComboBox()
        for label, key in RENAME_SCHEMAS:
            schema_combo.addItem(label, key)
        start_lbl = QLabel("Start:")
        start_lbl.setFixedWidth(36)
        start_spin = QSpinBox()
        start_spin.setRange(1, 9999)
        start_spin.setValue(1)
        start_spin.setFixedWidth(68)
        schema_row.addWidget(schema_lbl)
        schema_row.addWidget(schema_combo, 1)
        schema_row.addSpacing(12)
        schema_row.addWidget(start_lbl)
        schema_row.addWidget(start_spin)
        rename_layout.addLayout(schema_row)

        # Zeile 2: Kontextsensitives Extra-Feld (Schema 3+4)
        extra_row = QHBoxLayout()
        extra_lbl = QLabel("Wert:")
        extra_lbl.setFixedWidth(100)
        extra_edit = QLineEdit()
        extra_hint = QLabel("")
        extra_hint.setStyleSheet("color: #888888; font-size: 11px;")
        extra_row.addWidget(extra_lbl)
        extra_row.addWidget(extra_edit, 1)
        extra_row.addWidget(extra_hint)
        rename_layout.addLayout(extra_row)

        # Zeile 3: Prefix/Suffix für Schema 5
        affix_row = QHBoxLayout()
        affix_lbl = QLabel("Affix:")
        affix_lbl.setFixedWidth(100)
        prefix_edit = QLineEdit()
        prefix_edit.setPlaceholderText("Prefix…")
        affix_mid = QLabel("{name}")
        affix_mid.setStyleSheet("color: #888888; font-size: 11px; padding: 0 6px;")
        suffix_edit = QLineEdit()
        suffix_edit.setPlaceholderText("Suffix…")
        affix_row.addWidget(affix_lbl)
        affix_row.addWidget(prefix_edit, 1)
        affix_row.addWidget(affix_mid)
        affix_row.addWidget(suffix_edit, 1)
        rename_layout.addLayout(affix_row)

        ops_layout.addWidget(rename_frame)

        def _get_schema_key():
            return schema_combo.currentData()

        def _get_extra():
            key = _get_schema_key()
            if key == "name_affix":
                return f"{prefix_edit.text()}|||{suffix_edit.text()}"
            return extra_edit.text()

        def _update_rename_ui():
            key = _get_schema_key()
            needs_extra = key in ("pattern", "prefix_num")
            needs_affix = key == "name_affix"
            extra_lbl.setVisible(needs_extra)
            extra_edit.setVisible(needs_extra)
            extra_hint.setVisible(needs_extra)
            affix_lbl.setVisible(needs_affix)
            prefix_edit.setVisible(needs_affix)
            affix_mid.setVisible(needs_affix)
            suffix_edit.setVisible(needs_affix)
            if key == "pattern":
                extra_edit.setPlaceholderText("{name}_{index}")
                extra_hint.setText("Vars: {name}  {index}  {INDEX}")
            elif key == "prefix_num":
                extra_edit.setPlaceholderText("SONG")
                extra_hint.setText("Ergebnis: SONG001, SONG002 …")
            _update_preview()

        def _update_preview():
            is_rename = op_combo.currentText() == "Batch Umbenennen"
            rename_frame.setVisible(is_rename)
            item_table.setColumnHidden(2, not is_rename)
            if not is_rename:
                return
            schema = _get_schema_key()
            extra  = _get_extra()
            start  = start_spin.value()
            for row in range(item_table.rowCount()):
                data_cell = item_table.item(row, 1)
                if not data_cell:
                    continue
                itm = data_cell.data(Qt.UserRole)
                abs_idx = (start - 1) + row
                stem = _compute_rename(schema, extra, itm.name, abs_idx)
                new_name = stem if stem.lower().endswith(".xml") else stem + ".XML"
                prev_cell = item_table.item(row, 2)
                if prev_cell is None:
                    prev_cell = QTableWidgetItem()
                    item_table.setItem(row, 2, prev_cell)
                prev_cell.setText(new_name)
                color = QColor("#F39C12") if new_name != itm.file_path.name else QColor("#888888")
                prev_cell.setForeground(color)

        op_combo.currentIndexChanged.connect(_update_preview)
        schema_combo.currentIndexChanged.connect(_update_rename_ui)
        start_spin.valueChanged.connect(_update_preview)
        extra_edit.textChanged.connect(_update_preview)
        prefix_edit.textChanged.connect(_update_preview)
        suffix_edit.textChanged.connect(_update_preview)

        layout.addWidget(ops_frame)

        item_table = QTableWidget(0, 3)
        item_table.setHorizontalHeaderLabels(["✓", "Name", "Vorschau"])
        item_table.verticalHeader().setVisible(False)
        hv = item_table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.Fixed)
        hv.setSectionResizeMode(1, QHeaderView.Stretch)
        hv.setSectionResizeMode(2, QHeaderView.Stretch)
        item_table.setColumnWidth(0, 30)
        item_table.setColumnHidden(2, False)
        item_table.setAlternatingRowColors(True)
        layout.addWidget(item_table, 1)

        # Referenzen + Initialzustand (item_table muss vorher existieren)
        widget._schema_combo   = schema_combo
        widget._start_spin     = start_spin
        widget._get_extra      = _get_extra
        widget._update_preview = _update_preview
        widget._item_table     = item_table
        _update_rename_ui()   # Initialzustand setzen

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
            rename_params = {
                "schema":      widget._schema_combo.currentData(),
                "extra":       widget._get_extra(),
                "start_index": widget._start_spin.value(),
            }
            self._run_batch(selected, op_combo.currentText(), rename_params=rename_params)

        sel_all_btn.clicked.connect(sel_all)
        sel_none_btn.clicked.connect(sel_none)
        run_btn.clicked.connect(run_batch)

        widget._item_table = item_table
        widget._op_combo = op_combo
        return widget

    def _build_sample_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

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
    def set_staging(self, staging: StagingStore):
        self._staging = staging
        if hasattr(self, '_pending_panel'):
            self._pending_panel._staging = staging
            self._pending_panel.refresh()

    def update_index(self, index: SDCardIndex):
        self._index = index
        unused = len(index.unused_samples)
        self._unused_count_lbl.setText(f"{unused} ungenutzte Samples ({sum(s.size_mb for s in index.unused_samples):.1f} MB)")

        tabs_widget = self.findChild(QTabWidget)
        if not tabs_widget:
            return

        content_map = {
            "songs": index.songs,
            "kits": index.kits,
            "synths": index.synths,
        }
        for i in range(tabs_widget.count() - 2):
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
                    table.setItem(row, 2, QTableWidgetItem(""))
                # Preview nach Neubefüllung aktualisieren
                if hasattr(tab, "_update_preview"):
                    tab._update_preview()

    def _run_batch(self, items: list, operation_text: str, pattern: str = "", rename_params: dict = None):
        if not items:
            return

        op_map = {
            "Batch Umbenennen": "rename",
            "Batch Exportieren": "export",
            "Batch Löschen": "delete",
            "Volumes normalisieren": "normalize_volume",
            "Kit-Master begrenzen": "cap_kit_master",
            "Pad-Volumes begrenzen": "cap_pad_volumes",
            "Clip-Volumes begrenzen": "cap_clip_volumes",
        }
        op = op_map.get(operation_text, "")
        if not op:
            return

        params = rename_params.copy() if (op == "rename" and rename_params) else {"pattern": pattern}

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

        if op in ("cap_kit_master", "cap_pad_volumes", "cap_clip_volumes"):
            threshold, ok = QInputDialog.getInt(
                self, "Lautstärke begrenzen",
                f"Maximale Lautstärke für {len(items)} Dateien (0 – 50):",
                40, 0, 50, 1
            )
            if not ok:
                return
            params["threshold"] = threshold

        if self._worker and self._worker.isRunning():
            self._status.setText("⚠  Batch läuft noch, bitte warten…")
            return

        self._progress.setVisible(True)
        self._progress.setValue(0)

        self._worker = BatchWorker(items, op, params)
        self._worker.progress.connect(lambda p, m: (self._progress.setValue(p), self._status.setText(m)))
        self._worker.finished.connect(self._on_batch_done)
        self._worker.error.connect(lambda e: QMessageBox.warning(self, "Fehler", e))
        self._worker.start()

    def _on_batch_done(self, result: dict, pending: list):
        self._progress.setVisible(False)
        if self._staging and pending:
            for c in pending:
                self._staging.add(c)
            self._pending_panel.refresh()
            self._status.setText(
                f"⏳  {len(pending)} Änderungen vorgemerkt  |  "
                f"✅ {result['success']}/{result['total']}"
                + (f"  |  ⚠ {result['failed']} Fehler" if result["failed"] else "")
            )
            self.request_rescan.emit()
        else:
            # Fallback: direkt anwenden wenn kein Staging konfiguriert
            if pending:
                from ..core.file_ops import _write_xml
                for c in pending:
                    try:
                        if c.change_type == ChangeType.XML_EDIT:
                            _write_xml(c.file_path, c.new_content, c.encoding)
                        elif c.change_type == ChangeType.RENAME:
                            c.file_path.rename(c.file_path.parent / c.new_name)
                        elif c.change_type == ChangeType.DELETE:
                            c.file_path.unlink(missing_ok=True)
                    except Exception as e:
                        log.warning("Direkte Anwendung fehlgeschlagen (%s): %s", c.file_path.name, e)
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

        from ..core.sd_scanner import AUDIO_EXTENSIONS
        files = [f for f in src.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS]

        success = 0
        for f in files:
            try:
                dest = dest_root / f.name
                if not dest.exists():
                    shutil.copy2(str(f), str(dest))
                    success += 1
            except Exception as e:
                log.warning("Import fehlgeschlagen (%s): %s", f.name, e)

        self._status.setText(f"\u2705  {success}/{len(files)} Samples importiert nach {dest_subpath}")
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
        root_path = self._index.root_path
        total = len(samples)

        def _do_export(emit_progress):
            with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, s in enumerate(samples):
                    if s.file_path.exists():
                        try:
                            arcname = str(s.file_path.relative_to(root_path)).replace("\\", "/")
                            zf.write(s.file_path, arcname)
                        except Exception as e:
                            log.warning("Sample nicht exportiert (%s): %s", s.file_path.name, e)
                    emit_progress(int((i + 1) / max(total, 1) * 100))
            size_mb = Path(dest).stat().st_size / (1024 * 1024)
            return f"\u2705  {total} Samples exportiert ({size_mb:.1f} MB)"

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._simple_worker = SimpleWorker(_do_export)
        self._simple_worker.progress.connect(self._progress.setValue)
        self._simple_worker.finished.connect(lambda msg: (
            self._progress.setVisible(False),
            self._status.setText(msg),
        ))
        self._simple_worker.error.connect(lambda e: (
            self._progress.setVisible(False),
            QMessageBox.warning(self, "Fehler", e),
        ))
        self._simple_worker.start()

    def _delete_unused_samples(self):
        if not self._index:
            return
        unused = self._index.unused_samples
        if not unused:
            QMessageBox.information(self, "Info", "Keine ungenutzten Samples gefunden.")
            return

        total_mb = sum(s.size_mb for s in unused)
        reply = QMessageBox.warning(
            self, "Ungenutzte l\u00f6schen",
            f"{len(unused)} ungenutzte Samples ({total_mb:.1f} MB) l\u00f6schen?\n\nDiese Aktion kann nicht r\u00fcckg\u00e4ngig gemacht werden!",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        def _do_delete(emit_progress):
            deleted = 0
            for i, s in enumerate(unused):
                try:
                    s.file_path.unlink()
                    deleted += 1
                except Exception as e:
                    log.warning("L\u00f6schen fehlgeschlagen (%s): %s", s.file_path.name, e)
                emit_progress(int((i + 1) / max(len(unused), 1) * 100))
            return f"\ud83d\uddd1  {deleted} ungenutzte Samples gel\u00f6scht."

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._simple_worker = SimpleWorker(_do_delete)
        self._simple_worker.progress.connect(self._progress.setValue)
        self._simple_worker.finished.connect(lambda msg: (
            self._progress.setVisible(False),
            self._status.setText(msg),
            self.request_rescan.emit(),
        ))
        self._simple_worker.error.connect(lambda e: (
            self._progress.setVisible(False),
            QMessageBox.warning(self, "Fehler", e),
        ))
        self._simple_worker.start()

    def _validate_all_xmls(self):
        if not self._index:
            return
        from ..core.xml_parser import validate_xml_file

        errors = []
        total = 0
        for folder in ("SONGS", "KITS", "SYNTHS"):
            d = self._index.root_path / folder
            if not d.exists():
                continue
            seen_xml = set()
            xml_files = []
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() == ".xml" and f not in seen_xml:
                    seen_xml.add(f)
                    xml_files.append(f)
            for xml in xml_files:
                total += 1
                err = validate_xml_file(xml)
                if err:
                    errors.append(f"{xml.name}: {err}")

        if errors:
            self._validate_result.setText(
                f"\u26a0  {len(errors)}/{total} XML-Fehler:\n" + "\n".join(errors[:10])
            )
            self._validate_result.setStyleSheet("color: #E74C3C; font-size: 12px;")
        else:
            self._validate_result.setText(f"\u2705  Alle {total} XML-Dateien sind valide.")
            self._validate_result.setStyleSheet("color: #2ECC71; font-size: 12px;")

    def _confirm_global_replace(self, find_text: str, replace_text: str,
                                  preview: list) -> bool:
        """Show a preview dialog listing affected files + match count per
        file before any staging/writing happens. Returns True if the user
        confirms."""
        total = sum(count for _, count in preview)

        dialog = QDialog(self)
        dialog.setWindowTitle("Globales Ersetzen — Vorschau")
        layout = QVBoxLayout(dialog)

        header = QLabel(
            f"'{find_text}' → '{replace_text}'\n"
            f"{len(preview)} Datei(en) betroffen, {total} Treffer insgesamt:"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        list_widget = QListWidget()
        for file_path, count in preview:
            list_widget.addItem(f"{file_path.name}  —  {count} Treffer")
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Ersetzen")
        buttons.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.resize(440, 420)
        return dialog.exec() == QDialog.Accepted

    def _global_replace(self):
        if not self._index:
            return
        find_text = self._find_edit.text()
        replace_text = self._replace_edit.text()

        if not find_text:
            QMessageBox.warning(self, "Fehler", "Bitte Suchbegriff eingeben.")
            return

        seen_xml2 = set()
        xml_files = []
        for folder in ("SONGS", "KITS", "SYNTHS"):
            d = self._index.root_path / folder
            if not d.exists():
                continue
            for f in d.rglob("*"):
                if f.is_file() and f.suffix.lower() == ".xml" and f not in seen_xml2:
                    seen_xml2.add(f)
                    xml_files.append(f)

        from ..core.staging import plan_global_replace, preview_global_replace
        preview = preview_global_replace(xml_files, find_text)

        if not preview:
            self._status.setText("ℹ  Keine Treffer — keine Datei geändert.")
            return

        if not self._confirm_global_replace(find_text, replace_text, preview):
            return

        changes = plan_global_replace(xml_files, find_text, replace_text)

        if not changes:
            self._status.setText("ℹ  Keine Treffer — keine Datei geändert.")
            return

        if self._staging:
            # Stage the changes so the user can review/undo before they are
            # written to disk, instead of immediately overwriting every
            # matching XML across SONGS/KITS/SYNTHS with no way back.
            for c in changes:
                self._staging.add(c)
            self._status.setText(f"⏳  {len(changes)} XML-Dateien vorgemerkt (Staging).")
            self._pending_panel.refresh()
        else:
            from ..core.file_ops import _write_xml
            for c in changes:
                _write_xml(c.file_path, c.new_content, c.encoding)
            self._status.setText(f"✅  {len(changes)} XML-Dateien aktualisiert.")
            self.request_rescan.emit()
